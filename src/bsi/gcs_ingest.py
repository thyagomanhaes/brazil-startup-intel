"""Object paths in the raw bucket and streaming SHA-256 (task T3).

The raw bucket is write-once: the ingest service account can create objects
but never overwrite or delete them (D-043). Every fetch therefore gets its own
path, keyed by a UTC timestamp to the second (D-046, D-054). Files are
downloaded to a temp file and hashed in the same pass, then uploaded (D-053).
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import BinaryIO

# 8 MiB: flat memory for any file size, and a multiple of the 256 KiB unit
# that GCS resumable uploads require (AD-046).
CHUNK_SIZE = 8 * 1024 * 1024

SOURCES = frozenset({"cnpj", "cvm_registry"})

_MONTH = re.compile(r"\d{4}-\d{2}")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _check_period(period: str) -> None:
    """Accept a release month (YYYY-MM) or a snapshot day (YYYY-MM-DD)."""
    if _MONTH.fullmatch(period):
        fmt = "%Y-%m"
    elif _DAY.fullmatch(period):
        fmt = "%Y-%m-%d"
    else:
        raise ValueError(f"period must be YYYY-MM or YYYY-MM-DD, got {period!r}")
    try:
        datetime.strptime(period, fmt)
    except ValueError as exc:
        raise ValueError(f"period is not a real date: {period!r}") from exc


def _check_filename(filename: str) -> None:
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise ValueError(f"filename must be a plain file name, got {filename!r}")


def object_path(source: str, period: str, fetched_at: datetime, filename: str) -> str:
    """Build the raw object path for one fetched file.

    Example: raw/cnpj/2026-10/fetched=2026-11-09T140300Z/Empresas0.zip
    """
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}, expected one of {sorted(SOURCES)}")
    _check_period(period)
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise ValueError("fetched_at must carry a timezone")
    _check_filename(filename)
    stamp = fetched_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    return f"raw/{source}/{period}/fetched={stamp}/{filename}"


def sha256_stream(stream: BinaryIO, chunk_size: int = CHUNK_SIZE) -> tuple[str, int]:
    """Return (hex SHA-256, byte count) of a binary stream, read in chunks.

    The stream is never read whole, so memory stays flat for any file size.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(chunk_size):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size
