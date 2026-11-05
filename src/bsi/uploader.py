"""Upload a local file to the raw bucket only when its content is new (task T4).

Flow for one file (D-030, D-053, AD-049):
1. Hash the local temp file in chunks.
2. If the manifest already has this content for the same source, period and
   file name, skip. No call to GCS.
3. Otherwise upload to a new fetch-timestamp path (D-046, D-054), with the
   precondition "no object at this path" (AD-050), then record the manifest row.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import psycopg
from google.cloud.storage import Bucket

from bsi.gcs_ingest import CHUNK_SIZE, object_path, sha256_stream

_FIND = """
    SELECT object_path
    FROM raw.ingest_manifest
    WHERE source = %s AND period = %s AND source_name = %s AND sha256 = %s
"""

_INSERT = """
    INSERT INTO raw.ingest_manifest
        (object_path, source, period, source_name, source_url, sha256, size_bytes, fetched_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


@dataclass(frozen=True)
class UploadResult:
    status: Literal["uploaded", "skipped"]
    object_path: str
    sha256: str
    size_bytes: int


def upload_if_changed(
    *,
    bucket: Bucket,
    conn: psycopg.Connection,
    source: str,
    period: str,
    filename: str,
    local_path: Path | str,
    fetched_at: datetime,
    source_url: str | None = None,
) -> UploadResult:
    """Upload ``local_path`` unless the same content is already in the raw bucket.

    Raises google.api_core.exceptions.PreconditionFailed if an object already
    exists at the target path. Raw is write-once (D-043), so that is a bug in
    the caller, never something to retry.
    """
    with open(local_path, "rb") as fh:
        sha256, size = sha256_stream(fh)

    existing = conn.execute(_FIND, (source, period, filename, sha256)).fetchone()
    if existing:
        return UploadResult("skipped", existing[0], sha256, size)

    path = object_path(source, period, fetched_at, filename)
    blob = bucket.blob(path, chunk_size=CHUNK_SIZE)  # resumable, in 8 MiB chunks
    blob.metadata = {"sha256": sha256, "source_url": source_url or ""}
    blob.upload_from_filename(str(local_path), if_generation_match=0)

    with conn.transaction():
        conn.execute(
            _INSERT, (path, source, period, filename, source_url, sha256, size, fetched_at)
        )
    return UploadResult("uploaded", path, sha256, size)
