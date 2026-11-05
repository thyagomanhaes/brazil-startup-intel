"""T4: upload a local file to the raw bucket only when its content is new.

Runs against the GCS emulator (D-055) and the data Postgres (D-056).
Decisions: D-030, D-043, D-046, D-053, D-054, AD-048 to AD-050.
"""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from google.api_core.exceptions import PreconditionFailed
from google.auth.credentials import AnonymousCredentials
from google.cloud import storage

from bsi.uploader import upload_if_changed

MANIFEST_SQL = Path(__file__).resolve().parents[1] / "sql" / "raw" / "001_ingest_manifest.sql"
FETCHED = datetime(2026, 11, 9, 14, 3, 0, tzinfo=timezone.utc)


@pytest.fixture
def pg():
    conn = psycopg.connect(os.environ["DATA_PG_DSN"], autocommit=True)
    conn.execute(MANIFEST_SQL.read_text(encoding="utf-8"))
    conn.execute("TRUNCATE raw.ingest_manifest")
    yield conn
    conn.close()


@pytest.fixture
def bucket():
    client = storage.Client(project="test", credentials=AnonymousCredentials())
    deadline = time.monotonic() + 20
    while True:  # the emulator has no healthcheck, so wait until it answers
        try:
            list(client.list_buckets())
            break
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)
    return client.create_bucket(f"test-{uuid.uuid4().hex[:12]}")


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _upload(bucket, pg, local_path, fetched_at=FETCHED):
    return upload_if_changed(
        bucket=bucket,
        conn=pg,
        source="cnpj",
        period="2026-10",
        filename="Empresas0.zip",
        local_path=local_path,
        fetched_at=fetched_at,
        source_url="https://example.invalid/Empresas0.zip",
    )


def _manifest_rows(pg):
    return pg.execute(
        "SELECT object_path, sha256, size_bytes FROM raw.ingest_manifest ORDER BY fetched_at"
    ).fetchall()


def test_first_upload_writes_object_and_manifest_row(bucket, pg, tmp_path):
    local = _write(tmp_path, "Empresas0.zip", b"release one")
    result = _upload(bucket, pg, local)

    assert result.status == "uploaded"
    assert result.object_path == "raw/cnpj/2026-10/fetched=2026-11-09T140300Z/Empresas0.zip"
    assert bucket.blob(result.object_path).download_as_bytes() == b"release one"
    assert _manifest_rows(pg) == [(result.object_path, result.sha256, 11)]


def test_same_content_again_is_skipped_without_new_object(bucket, pg, tmp_path):
    local = _write(tmp_path, "Empresas0.zip", b"release one")
    first = _upload(bucket, pg, local)
    second = _upload(bucket, pg, local, fetched_at=FETCHED + timedelta(hours=1))

    assert second.status == "skipped"
    assert second.object_path == first.object_path
    assert [b.name for b in bucket.list_blobs()] == [first.object_path]
    assert len(_manifest_rows(pg)) == 1


def test_changed_content_lands_under_a_new_path_and_keeps_the_old_one(bucket, pg, tmp_path):
    first = _upload(bucket, pg, _write(tmp_path, "a.zip", b"release one"))
    second = _upload(
        bucket, pg, _write(tmp_path, "b.zip", b"release two"),
        fetched_at=FETCHED + timedelta(hours=1),
    )

    assert second.status == "uploaded"
    assert second.object_path != first.object_path
    assert bucket.blob(first.object_path).download_as_bytes() == b"release one"
    assert bucket.blob(second.object_path).download_as_bytes() == b"release two"
    assert len(_manifest_rows(pg)) == 2


def test_existing_path_is_never_overwritten(bucket, pg, tmp_path):
    first = _upload(bucket, pg, _write(tmp_path, "a.zip", b"release one"))

    with pytest.raises(PreconditionFailed):
        _upload(bucket, pg, _write(tmp_path, "b.zip", b"release two"))  # same fetched_at

    assert bucket.blob(first.object_path).download_as_bytes() == b"release one"
    assert len(_manifest_rows(pg)) == 1


def test_object_metadata_carries_the_sha256(bucket, pg, tmp_path):
    result = _upload(bucket, pg, _write(tmp_path, "a.zip", b"release one"))
    blob = bucket.get_blob(result.object_path)
    assert blob.metadata["sha256"] == result.sha256


def test_manifest_refuses_the_same_content_twice(pg):
    row = ("cnpj", "2026-10", "Empresas0.zip", "a" * 64, 1, FETCHED)
    insert = (
        "INSERT INTO raw.ingest_manifest "
        "(object_path, source, period, source_name, sha256, size_bytes, fetched_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
    )
    pg.execute(insert, ("raw/one", *row))
    with pytest.raises(psycopg.errors.UniqueViolation):
        pg.execute(insert, ("raw/two", *row))
