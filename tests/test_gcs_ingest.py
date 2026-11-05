"""T3: object paths in the raw bucket and streaming SHA-256.

Decisions: D-043 (no overwrite), D-046 (new path per fetch), D-053 (temp file,
then upload), D-054 (UTC timestamp in the path), AD-044, AD-046.
"""
import hashlib
import io
from datetime import datetime, timedelta, timezone

import pytest

from bsi.gcs_ingest import CHUNK_SIZE, object_path, sha256_stream

FETCHED = datetime(2026, 11, 9, 14, 3, 0, tzinfo=timezone.utc)


# --- object_path -----------------------------------------------------------

def test_cnpj_path_has_period_and_utc_fetch_timestamp():
    assert (
        object_path("cnpj", "2026-10", FETCHED, "Empresas0.zip")
        == "raw/cnpj/2026-10/fetched=2026-11-09T140300Z/Empresas0.zip"
    )


def test_daily_period_is_accepted_for_daily_sources():
    assert (
        object_path("cvm_registry", "2026-11-09", FETCHED, "cad_plataforma.csv")
        == "raw/cvm_registry/2026-11-09/fetched=2026-11-09T140300Z/cad_plataforma.csv"
    )


def test_fetch_time_in_another_timezone_is_converted_to_utc():
    fortaleza = timezone(timedelta(hours=-3))
    local = datetime(2026, 11, 9, 11, 3, 0, tzinfo=fortaleza)
    assert object_path("cnpj", "2026-10", local, "Empresas0.zip") == object_path(
        "cnpj", "2026-10", FETCHED, "Empresas0.zip"
    )


def test_two_fetches_one_second_apart_never_share_a_path():
    later = FETCHED + timedelta(seconds=1)
    assert object_path("cnpj", "2026-10", FETCHED, "Empresas0.zip") != object_path(
        "cnpj", "2026-10", later, "Empresas0.zip"
    )


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        object_path("cnpj", "2026-10", datetime(2026, 11, 9, 14, 3), "Empresas0.zip")


def test_unknown_source_is_rejected():
    with pytest.raises(ValueError, match="source"):
        object_path("receita", "2026-10", FETCHED, "Empresas0.zip")


@pytest.mark.parametrize("period", ["2026-13", "2026-1", "202610", "2026-10-32", ""])
def test_invalid_period_is_rejected(period):
    with pytest.raises(ValueError, match="period"):
        object_path("cnpj", period, FETCHED, "Empresas0.zip")


@pytest.mark.parametrize("filename", ["", "..", "a/b.zip", "a\\b.zip", "../x.zip"])
def test_filename_cannot_escape_its_folder(filename):
    with pytest.raises(ValueError, match="filename"):
        object_path("cnpj", "2026-10", FETCHED, filename)


# --- sha256_stream ---------------------------------------------------------

def test_sha256_of_known_bytes():
    digest, size = sha256_stream(io.BytesIO(b"abc"))
    assert digest == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert size == 3


def test_sha256_of_empty_stream():
    digest, size = sha256_stream(io.BytesIO(b""))
    assert digest == hashlib.sha256(b"").hexdigest()
    assert size == 0


def test_chunk_size_does_not_change_the_result():
    data = bytes(range(256)) * 1000
    small = sha256_stream(io.BytesIO(data), chunk_size=7)
    default = sha256_stream(io.BytesIO(data))
    assert small == default == (hashlib.sha256(data).hexdigest(), len(data))


class _ReadSpy(io.BytesIO):
    """Records every read size, to prove the stream is never read whole."""

    def __init__(self, data):
        super().__init__(data)
        self.sizes = []

    def read(self, size=-1):
        self.sizes.append(size)
        return super().read(size)


def test_stream_is_read_in_bounded_chunks():
    spy = _ReadSpy(b"x" * 100)
    sha256_stream(spy, chunk_size=10)
    assert spy.sizes and all(0 < s <= 10 for s in spy.sizes)


def test_default_chunk_size_is_8_mib():
    assert CHUNK_SIZE == 8 * 1024 * 1024
