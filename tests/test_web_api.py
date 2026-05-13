"""
Tests for the FastAPI web application and job routes.

Covers:
- App creation and CORS configuration
- POST /api/jobs  (job creation, file upload, metadata fields)
- GET  /api/jobs/{job_id}  (status polling)
- GET  /api/jobs/{job_id}/results  (CSV download)
- GET  /api/jobs/{job_id}/masks/{filename}  (mask download)
- 404 / 409 error responses
"""

import io
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_jobs_dir(tmp_path, monkeypatch):
    """Redirect JOBS_DIR and DB_PATH to a temp directory for each test."""
    import sedimental.web as web_module
    monkeypatch.setattr(web_module, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(web_module, "DB_PATH", tmp_path / "jobs.db")
    return tmp_path


@pytest.fixture()
def client(tmp_jobs_dir, monkeypatch):
    """Return a TestClient with a fresh app and isolated DB.

    Background job processing is patched out so tests don't trigger the
    real processing pipeline (which would attempt to initialise PyImageJ).
    """
    import sedimental.web as web_module
    from sedimental.web import create_app, init_db
    # Prevent background tasks from running the real processing pipeline
    monkeypatch.setattr(web_module, "_run_job", lambda *args, **kwargs: None)
    # Initialise the DB before any requests so the table exists
    init_db()
    app = create_app()
    return TestClient(app, raise_server_exceptions=True)


def _make_jpeg_bytes() -> bytes:
    """Return a minimal valid JPEG byte string via Pillow."""
    from PIL import Image
    buf = io.BytesIO()
    img = Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8))
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# App-level tests
# ---------------------------------------------------------------------------

class TestAppCreation:
    def test_create_app_returns_fastapi(self):
        from fastapi import FastAPI
        from sedimental.web import create_app
        app = create_app()
        assert isinstance(app, FastAPI)

    def test_cors_middleware_present(self):
        from fastapi.middleware.cors import CORSMiddleware
        from sedimental.web import create_app
        app = create_app()
        # Check middleware stack for CORSMiddleware (works across FastAPI versions)
        middleware_classes = [
            m.cls if hasattr(m, "cls") else type(m)
            for m in app.user_middleware
        ]
        assert CORSMiddleware in middleware_classes

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_root_endpoint(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Sedimental" in resp.text


# ---------------------------------------------------------------------------
# POST /api/jobs
# ---------------------------------------------------------------------------

class TestCreateJob:
    def test_create_job_returns_201(self, client):
        jpeg = _make_jpeg_bytes()
        resp = client.post(
            "/api/jobs",
            files=[("files", ("sample.jpg", jpeg, "image/jpeg"))],
        )
        assert resp.status_code == 201

    def test_create_job_response_shape(self, client):
        jpeg = _make_jpeg_bytes()
        resp = client.post(
            "/api/jobs",
            files=[("files", ("sample.jpg", jpeg, "image/jpeg"))],
        )
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert "sample.jpg" in data["files"]

    def test_create_job_multiple_files(self, client):
        jpeg = _make_jpeg_bytes()
        resp = client.post(
            "/api/jobs",
            files=[
                ("files", ("a.jpg", jpeg, "image/jpeg")),
                ("files", ("b.jpg", jpeg, "image/jpeg")),
            ],
        )
        assert resp.status_code == 201
        assert len(resp.json()["files"]) == 2

    def test_create_job_with_metadata_fields(self, client):
        jpeg = _make_jpeg_bytes()
        resp = client.post(
            "/api/jobs",
            files=[("files", ("sample.jpg", jpeg, "image/jpeg"))],
            data={
                "sample_id": "S001",
                "location_lat": "51.5",
                "location_lon": "-0.1",
                "capture_date": "2024-06-01",
                "scale_ppm": "10.5",
                "submitted_by": "alice",
                "save_masks": "true",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"

    def test_create_job_files_saved_to_disk(self, client, tmp_jobs_dir):
        jpeg = _make_jpeg_bytes()
        resp = client.post(
            "/api/jobs",
            files=[("files", ("sample.jpg", jpeg, "image/jpeg"))],
        )
        job_id = resp.json()["job_id"]
        saved = tmp_jobs_dir / job_id / "input" / "sample.jpg"
        assert saved.exists()
        assert saved.read_bytes() == jpeg

    def test_create_job_persisted_in_db(self, client, tmp_jobs_dir):
        jpeg = _make_jpeg_bytes()
        resp = client.post(
            "/api/jobs",
            files=[("files", ("sample.jpg", jpeg, "image/jpeg"))],
        )
        job_id = resp.json()["job_id"]
        conn = sqlite3.connect(str(tmp_jobs_dir / "jobs.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
        assert row is not None
        assert row["status"] in ("pending", "processing", "completed", "failed")

    def test_create_job_no_files_returns_422(self, client):
        resp = client.post("/api/jobs", data={"sample_id": "S001"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}
# ---------------------------------------------------------------------------

class TestGetJobStatus:
    def _create(self, client):
        jpeg = _make_jpeg_bytes()
        resp = client.post(
            "/api/jobs",
            files=[("files", ("sample.jpg", jpeg, "image/jpeg"))],
        )
        return resp.json()["job_id"]

    def test_get_job_status_200(self, client):
        job_id = self._create(client)
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200

    def test_get_job_status_shape(self, client):
        job_id = self._create(client)
        data = client.get(f"/api/jobs/{job_id}").json()
        assert data["job_id"] == job_id
        assert data["status"] in ("pending", "processing", "completed", "failed")
        assert "progress" in data
        assert "current" in data["progress"]
        assert "total" in data["progress"]
        assert "files" in data

    def test_get_job_status_404_unknown(self, client):
        resp = client.get("/api/jobs/does-not-exist")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/results
# ---------------------------------------------------------------------------

class TestDownloadResults:
    def _seed_completed_job(self, tmp_jobs_dir):
        """Insert a completed job row and create a fake CSV on disk."""
        import uuid
        from sedimental.web import init_db
        init_db()
        job_id = str(uuid.uuid4())
        output_dir = tmp_jobs_dir / job_id / "output"
        output_dir.mkdir(parents=True)
        csv_path = output_dir / "results.csv"
        csv_path.write_text("source_file,grain_id\nsample.jpg,1\n")

        conn = sqlite3.connect(str(tmp_jobs_dir / "jobs.db"))
        conn.execute(
            """INSERT INTO jobs (id, status, input_files, save_masks, result_path)
               VALUES (?, 'completed', '[]', 0, ?)""",
            (job_id, str(csv_path)),
        )
        conn.commit()
        conn.close()
        return job_id

    def test_download_results_200(self, client, tmp_jobs_dir):
        job_id = self._seed_completed_job(tmp_jobs_dir)
        resp = client.get(f"/api/jobs/{job_id}/results")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_download_results_content(self, client, tmp_jobs_dir):
        job_id = self._seed_completed_job(tmp_jobs_dir)
        resp = client.get(f"/api/jobs/{job_id}/results")
        assert "source_file" in resp.text

    def test_download_results_404_unknown_job(self, client):
        resp = client.get("/api/jobs/no-such-job/results")
        assert resp.status_code == 404

    def test_download_results_409_not_completed(self, client, tmp_jobs_dir):
        import uuid
        from sedimental.web import init_db
        init_db()
        job_id = str(uuid.uuid4())
        conn = sqlite3.connect(str(tmp_jobs_dir / "jobs.db"))
        conn.execute(
            "INSERT INTO jobs (id, status, input_files, save_masks) VALUES (?, 'pending', '[]', 0)",
            (job_id,),
        )
        conn.commit()
        conn.close()
        resp = client.get(f"/api/jobs/{job_id}/results")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/masks/{filename}
# ---------------------------------------------------------------------------

class TestDownloadMask:
    def _seed_completed_job_with_mask(self, tmp_jobs_dir, mask_filename="sample_mask.tiff"):
        import uuid
        from sedimental.web import init_db
        init_db()
        job_id = str(uuid.uuid4())
        mask_dir = tmp_jobs_dir / job_id / "output" / "masks"
        mask_dir.mkdir(parents=True)
        (mask_dir / mask_filename).write_bytes(b"TIFF_PLACEHOLDER")

        conn = sqlite3.connect(str(tmp_jobs_dir / "jobs.db"))
        conn.execute(
            "INSERT INTO jobs (id, status, input_files, save_masks) VALUES (?, 'completed', '[]', 1)",
            (job_id,),
        )
        conn.commit()
        conn.close()
        return job_id

    def test_download_mask_200(self, client, tmp_jobs_dir):
        job_id = self._seed_completed_job_with_mask(tmp_jobs_dir)
        resp = client.get(f"/api/jobs/{job_id}/masks/sample_mask.tiff")
        assert resp.status_code == 200
        assert "tiff" in resp.headers["content-type"]

    def test_download_mask_404_unknown_job(self, client):
        resp = client.get("/api/jobs/no-such-job/masks/foo.tiff")
        assert resp.status_code == 404

    def test_download_mask_404_unknown_file(self, client, tmp_jobs_dir):
        job_id = self._seed_completed_job_with_mask(tmp_jobs_dir)
        resp = client.get(f"/api/jobs/{job_id}/masks/nonexistent.tiff")
        assert resp.status_code == 404

    def test_download_mask_409_not_completed(self, client, tmp_jobs_dir):
        import uuid
        from sedimental.web import init_db
        init_db()
        job_id = str(uuid.uuid4())
        conn = sqlite3.connect(str(tmp_jobs_dir / "jobs.db"))
        conn.execute(
            "INSERT INTO jobs (id, status, input_files, save_masks) VALUES (?, 'processing', '[]', 1)",
            (job_id,),
        )
        conn.commit()
        conn.close()
        resp = client.get(f"/api/jobs/{job_id}/masks/foo.tiff")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# File upload validation (Requirements 7.7, 7.8)
# ---------------------------------------------------------------------------

class TestFileUploadValidation:
    """Tests for JPEG validation and file size enforcement."""

    def test_non_jpeg_file_returns_400(self, client):
        """Uploading a PNG (non-JPEG) should return 400 with a descriptive message."""
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # PNG magic bytes
        resp = client.post(
            "/api/jobs",
            files=[("files", ("image.png", png_bytes, "image/png"))],
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "not a valid JPEG" in detail or "JPEG" in detail

    def test_non_jpeg_plain_text_returns_400(self, client):
        """Uploading a plain text file should return 400."""
        resp = client.post(
            "/api/jobs",
            files=[("files", ("notes.txt", b"hello world", "text/plain"))],
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "JPEG" in detail

    def test_file_exceeding_size_limit_returns_400(self, client, monkeypatch):
        """Uploading a file larger than the size limit should return 400 mentioning the size limit."""
        import sedimental.web as web_module
        # Use a tiny limit so we don't allocate 50 MB in the test container
        monkeypatch.setattr(web_module, "MAX_FILE_SIZE_BYTES", 100)
        # JPEG magic bytes + enough padding to exceed 100 bytes
        oversized = b"\xff\xd8\xff" + b"\x00" * 200
        resp = client.post(
            "/api/jobs",
            files=[("files", ("big.jpg", oversized, "image/jpeg"))],
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        # Message must mention the size limit
        assert "MB" in detail or "maximum" in detail.lower() or "size" in detail.lower()

    def test_valid_jpeg_upload_succeeds(self, client):
        """A valid JPEG should still be accepted (regression guard)."""
        jpeg = _make_jpeg_bytes()
        resp = client.post(
            "/api/jobs",
            files=[("files", ("sample.jpg", jpeg, "image/jpeg"))],
        )
        assert resp.status_code == 201

    def test_non_jpeg_error_message_includes_filename(self, client):
        """The 400 error detail should reference the offending filename."""
        bad_bytes = b"GIF89a" + b"\x00" * 50  # GIF magic bytes
        resp = client.post(
            "/api/jobs",
            files=[("files", ("photo.gif", bad_bytes, "image/gif"))],
        )
        assert resp.status_code == 400
        assert "photo.gif" in resp.json()["detail"]

    def test_size_limit_error_message_includes_filename(self, client, monkeypatch):
        """The 400 size-limit error detail should reference the offending filename."""
        import sedimental.web as web_module
        monkeypatch.setattr(web_module, "MAX_FILE_SIZE_BYTES", 100)
        oversized = b"\xff\xd8\xff" + b"\x00" * 200
        resp = client.post(
            "/api/jobs",
            files=[("files", ("huge.jpg", oversized, "image/jpeg"))],
        )
        assert resp.status_code == 400
        assert "huge.jpg" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Static file serving (favicon)
# ---------------------------------------------------------------------------

class TestFaviconServing:
    """Tests for favicon static file serving (Requirement 6.4)."""

    def test_favicon_returns_200(self, client):
        """GET /static/favicon.png should return HTTP 200.
        
        **Validates: Requirement 6.4**
        """
        resp = client.get("/static/favicon.png")
        assert resp.status_code == 200

    def test_favicon_content_type_is_png(self, client):
        """GET /static/favicon.png should return content-type image/png.
        
        **Validates: Requirement 6.4**
        """
        resp = client.get("/static/favicon.png")
        assert resp.status_code == 200
        assert "image/png" in resp.headers["content-type"]
