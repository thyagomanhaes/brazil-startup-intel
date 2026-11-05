-- One row per object written to the raw bucket (D-030, D-056).
-- The UNIQUE constraint makes "same content, uploaded once" a database rule,
-- so two concurrent runs cannot record the same file twice (AD-048).
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.ingest_manifest (
    object_path  text        PRIMARY KEY,
    source       text        NOT NULL,
    period       text        NOT NULL,
    source_name  text        NOT NULL,
    source_url   text,
    sha256       char(64)    NOT NULL,
    size_bytes   bigint      NOT NULL CHECK (size_bytes >= 0),
    fetched_at   timestamptz NOT NULL,
    uploaded_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, period, source_name, sha256)
);
