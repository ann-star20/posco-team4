-- AOI images stay on Jetson; only provenance and storage state live here.
CREATE TABLE aoi_image_artifacts (
    artifact_id UUID PRIMARY KEY,
    job_id UUID NOT NULL,
    attempt INTEGER NOT NULL CHECK (attempt > 0),
    source_event_id UUID REFERENCES events(event_id),
    image_role TEXT NOT NULL CHECK (image_role IN ('original', 'annotated')),
    device_id TEXT NOT NULL CHECK (length(btrim(device_id)) > 0),
    local_directory TEXT NOT NULL CHECK (
        local_directory LIKE '/%'
        AND local_directory NOT LIKE '%/'
        AND local_directory NOT LIKE '%//%'
        AND local_directory !~ '(^|/)\.{1,2}(/|$)'
        AND position(chr(92) in local_directory) = 0
    ),
    file_name TEXT NOT NULL CHECK (
        file_name ~ '^[^/]+\.[jJ][pP][gG]$'
        AND position(chr(92) in file_name) = 0
    ),
    local_path TEXT GENERATED ALWAYS AS (local_directory || '/' || file_name) STORED,
    content_type TEXT NOT NULL DEFAULT 'image/jpeg' CHECK (content_type = 'image/jpeg'),
    sha256 TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    byte_size BIGINT NOT NULL CHECK (byte_size > 0),
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    captured_at TIMESTAMPTZ NOT NULL,
    local_status TEXT NOT NULL DEFAULT 'ready' CHECK (local_status IN ('ready', 'missing', 'deleted')),
    cloud_status TEXT NOT NULL DEFAULT 'disabled'
      CHECK (cloud_status IN ('disabled', 'pending', 'uploading', 'uploaded', 'failed')),
    cloud_provider TEXT CHECK (cloud_provider IN ('gcs', 'google_drive')),
    cloud_object_key TEXT CHECK (length(btrim(cloud_object_key)) > 0),
    cloud_uploaded_at TIMESTAMPTZ,
    cloud_error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, attempt, image_role),
    UNIQUE (device_id, local_path),
    CHECK (cloud_status = 'disabled' OR cloud_provider IS NOT NULL),
    CHECK (cloud_status <> 'uploaded' OR
      (cloud_object_key IS NOT NULL AND cloud_uploaded_at IS NOT NULL)),
    CHECK (cloud_uploaded_at IS NULL OR cloud_status = 'uploaded'),
    CHECK (local_status <> 'deleted' OR cloud_status = 'uploaded')
);

CREATE INDEX aoi_image_artifacts_captured_idx ON aoi_image_artifacts(captured_at);
CREATE INDEX aoi_image_artifacts_event_idx ON aoi_image_artifacts(source_event_id)
    WHERE source_event_id IS NOT NULL;
CREATE INDEX aoi_image_artifacts_cloud_pending_idx ON aoi_image_artifacts(updated_at)
    WHERE cloud_status IN ('pending', 'uploading', 'failed');

COMMENT ON COLUMN aoi_image_artifacts.local_directory IS 'Jetson absolute directory, without trailing slash';
COMMENT ON COLUMN aoi_image_artifacts.file_name IS 'JPG basename, never a relative path';
COMMENT ON COLUMN aoi_image_artifacts.local_path IS 'Generated absolute Jetson path; not a public URL';
COMMENT ON COLUMN aoi_image_artifacts.cloud_object_key IS 'Durable bucket/object key or Drive file ID, not an expiring signed URL';
COMMENT ON COLUMN aoi_image_artifacts.updated_at IS 'Writer must update explicitly on storage state changes';
