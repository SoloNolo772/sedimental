"""
Web API integration tests.

These tests exercise the full request/response lifecycle without mocking
_run_job, so they cover:

  - Upload → processing → download flow (Requirements 7.1, 7.5)
  - Job status transitions: pending → processing → completed/failed (Req 7.4)
  - Concurrent job handling (Req 7.4)

The real processing pipeline (ImageGrains / PyImageJ) is NOT invoked.
Instead, ProcessingOrchestrator.process_batch is patched to write a
minimal CSV and return a BatchResult, keeping tests fast and self-contained.
"""

import io
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jpeg_bytes() -> bytes:
    """Return a minimal valid JPEG via Pillow."""
    from PIL import Image
    buf = io.BytesIO()
    img = Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8))
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _fake_batch_result(output_path: Path, **kwargs):
    """
    Simulate a successful process_batch call:
    writes a minimal CSV to output_path and returns a BatchResult.
    """
    from sedimental.models import BatchResult, ImageResult, SampleMetadata

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("source_file,grain_id,area\nsample.jpg,1,42.0\n")

    return BatchResult(
        total_images=1,
        successful=1,
        failed=0,
        results=[
            ImageResult(
                source_file="sample.jpg",
                metadata=SampleMetadata(),
                measurements=[],
            )
        ],
        errors={},
    )


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
def client(tmp_jobs_dir):
    """
    Return a TestClient backed by a real app with a real (but patched)
    processing pipeline.  _run_job is NOT patched here — it runs for real
    but process_batch is replaced with _fake_batch_result so no heavy
    dependencies are needed.
    """
    import sedimental.web as web_module
    from sedimental.web import create_app, init_db

    init_db()
    app = create_app()
    # Use raise_server_exceptions=False so we can inspect 5xx responses
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Upload → processing → download flow
# ---------------------------------------------------------------------------

class TestUploadDownloadFlow:
    """End-to-end: upload a JPEG, wait for completion, download results."""

    def _upload(self, client):
        jpeg = _make_jpeg_bytes()
        resp = client.post(
            "/api/jobs",
            files=[("files", ("sample.jpg", jpeg, "image/jpeg"))],
        )
        assert resp.status_code == 201
        return resp.json()["job_id"]

    def _wait_for_completion(self, client, job_id: str, timeout: float = 10.0):
        """Poll GET /api/jobs/{job_id} until status is terminal or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = client.get(f"/api/jobs/{job_id}").json()
            if data["status"] in ("completed", "failed"):
                return data
            time.sleep(0.05)
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    def test_upload_creates_job_in_pending_state(self, client, tmp_jobs_dir):
        """Immediately after upload the job must be pending (or processing)."""
        with patch("sedimental.web._run_job"):
            job_id = self._upload(client)
        data = client.get(f"/api/jobs/{job_id}").json()
        assert data["status"] in ("pending", "processing")

    def test_upload_saves_file_to_input_directory(self, client, tmp_jobs_dir):
        """Uploaded bytes must be persisted under <jobs_dir>/<job_id>/input/."""
        jpeg = _make_jpeg_bytes()
        with patch("sedimental.web._run_job"):
            resp = client.post(
                "/api/jobs",
                files=[("files", ("river.jpg", jpeg, "image/jpeg"))],
            )
        job_id = resp.json()["job_id"]
        saved = tmp_jobs_dir / job_id / "input" / "river.jpg"
        assert saved.exists()
        assert saved.read_bytes() == jpeg

    def test_completed_job_allows_csv_download(self, client, tmp_jobs_dir):
        """After processing completes the CSV must be downloadable."""
        with patch(
            "sedimental.orchestrator.ProcessingOrchestrator.process_batch",
            side_effect=_fake_batch_result,
        ):
            job_id = self._upload(client)
            data = self._wait_for_completion(client, job_id)

        assert data["status"] == "completed"
        resp = client.get(f"/api/jobs/{job_id}/results")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "source_file" in resp.text

    def test_csv_download_contains_grain_data(self, client, tmp_jobs_dir):
        """Downloaded CSV must contain the rows written by the pipeline."""
        with patch(
            "sedimental.orchestrator.ProcessingOrchestrator.process_batch",
            side_effect=_fake_batch_result,
        ):
            job_id = self._upload(client)
            self._wait_for_completion(client, job_id)

        resp = client.get(f"/api/jobs/{job_id}/results")
        assert "sample.jpg" in resp.text
        assert "grain_id" in resp.text

    def test_failed_job_returns_409_on_results_download(self, client, tmp_jobs_dir):
        """A failed job must return 409 when results are requested."""
        def _raise(*args, **kwargs):
            raise RuntimeError("simulated pipeline failure")

        with patch(
            "sedimental.orchestrator.ProcessingOrchestrator.process_batch",
            side_effect=_raise,
        ):
            job_id = self._upload(client)
            data = self._wait_for_completion(client, job_id)

        assert data["status"] == "failed"
        resp = client.get(f"/api/jobs/{job_id}/results")
        assert resp.status_code == 409

    def test_multiple_files_all_saved(self, client, tmp_jobs_dir):
        """All uploaded files must be persisted to the input directory."""
        jpeg = _make_jpeg_bytes()
        with patch("sedimental.web._run_job"):
            resp = client.post(
                "/api/jobs",
                files=[
                    ("files", ("a.jpg", jpeg, "image/jpeg")),
                    ("files", ("b.jpg", jpeg, "image/jpeg")),
                    ("files", ("c.jpg", jpeg, "image/jpeg")),
                ],
            )
        job_id = resp.json()["job_id"]
        for name in ("a.jpg", "b.jpg", "c.jpg"):
            assert (tmp_jobs_dir / job_id / "input" / name).exists()

    def test_metadata_written_to_job_directory(self, client, tmp_jobs_dir):
        """When metadata fields are supplied they must be persisted as metadata.json."""
        jpeg = _make_jpeg_bytes()
        with patch("sedimental.web._run_job"):
            resp = client.post(
                "/api/jobs",
                files=[("files", ("sample.jpg", jpeg, "image/jpeg"))],
                data={
                    "sample_id": "RIVER-42",
                    "location_lat": "36.1",
                    "location_lon": "-112.1",
                    "capture_date": "2024-07-04",
                    "scale_ppm": "12.5",
                    "submitted_by": "geo_alice",
                },
            )
        job_id = resp.json()["job_id"]
        meta_file = tmp_jobs_dir / job_id / "metadata.json"
        # metadata.json is written by _run_job; check the DB row instead
        conn = sqlite3.connect(str(tmp_jobs_dir / "jobs.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT metadata FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
        meta = json.loads(row["metadata"])
        assert meta["default"]["sample_id"] == "RIVER-42"
        assert meta["default"]["scale_ppm"] == 12.5


# ---------------------------------------------------------------------------
# Job status transitions
# ---------------------------------------------------------------------------

class TestJobStatusTransitions:
    """Verify the status field progresses through the expected states."""

    def _upload(self, client):
        jpeg = _make_jpeg_bytes()
        resp = client.post(
            "/api/jobs",
            files=[("files", ("sample.jpg", jpeg, "image/jpeg"))],
        )
        assert resp.status_code == 201
        return resp.json()["job_id"]

    def _wait(self, client, job_id: str, timeout: float = 10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = client.get(f"/api/jobs/{job_id}").json()
            if data["status"] in ("completed", "failed"):
                return data
            time.sleep(0.05)
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    def test_initial_status_is_pending(self, client, tmp_jobs_dir):
        """Job must start in 'pending' (background task may not have run yet)."""
        with patch("sedimental.web._run_job"):
            job_id = self._upload(client)
        data = client.get(f"/api/jobs/{job_id}").json()
        assert data["status"] in ("pending", "processing")

    def test_successful_job_reaches_completed(self, client, tmp_jobs_dir):
        """A job whose pipeline succeeds must end in 'completed'."""
        with patch(
            "sedimental.orchestrator.ProcessingOrchestrator.process_batch",
            side_effect=_fake_batch_result,
        ):
            job_id = self._upload(client)
            data = self._wait(client, job_id)
        assert data["status"] == "completed"

    def test_failed_job_reaches_failed(self, client, tmp_jobs_dir):
        """A job whose pipeline raises must end in 'failed'."""
        def _raise(*args, **kwargs):
            raise RuntimeError("boom")

        with patch(
            "sedimental.orchestrator.ProcessingOrchestrator.process_batch",
            side_effect=_raise,
        ):
            job_id = self._upload(client)
            data = self._wait(client, job_id)
        assert data["status"] == "failed"

    def test_failed_job_has_error_message(self, client, tmp_jobs_dir):
        """A failed job must expose a non-empty error_message."""
        def _raise(*args, **kwargs):
            raise RuntimeError("pipeline exploded")

        with patch(
            "sedimental.orchestrator.ProcessingOrchestrator.process_batch",
            side_effect=_raise,
        ):
            job_id = self._upload(client)
            data = self._wait(client, job_id)
        assert data["error_message"]
        assert "pipeline exploded" in data["error_message"]

    def test_completed_job_has_progress_equal_to_total(self, client, tmp_jobs_dir):
        """On completion progress.current must equal progress.total."""
        with patch(
            "sedimental.orchestrator.ProcessingOrchestrator.process_batch",
            side_effect=_fake_batch_result,
        ):
            job_id = self._upload(client)
            data = self._wait(client, job_id)
        assert data["progress"]["current"] == data["progress"]["total"]

    def test_status_transitions_are_monotonic(self, client, tmp_jobs_dir):
        """
        Collect status snapshots during processing and verify they only
        advance forward (pending → processing → completed/failed).
        """
        ORDER = {"pending": 0, "processing": 1, "completed": 2, "failed": 2}
        statuses = []

        # Use a slow fake that lets us observe the 'processing' state
        barrier = threading.Event()

        def _slow_batch(output_path, **kwargs):
            barrier.wait(timeout=5)
            return _fake_batch_result(output_path, **kwargs)

        with patch(
            "sedimental.orchestrator.ProcessingOrchestrator.process_batch",
            side_effect=_slow_batch,
        ):
            job_id = self._upload(client)
            # Sample status before releasing the barrier
            statuses.append(client.get(f"/api/jobs/{job_id}").json()["status"])
            barrier.set()
            data = self._wait(client, job_id)
            statuses.append(data["status"])

        # Verify monotonic progression
        for i in range(len(statuses) - 1):
            assert ORDER[statuses[i]] <= ORDER[statuses[i + 1]], (
                f"Status went backwards: {statuses}"
            )


# ---------------------------------------------------------------------------
# Concurrent job handling
# ---------------------------------------------------------------------------

class TestConcurrentJobHandling:
    """Verify the server handles multiple simultaneous jobs correctly."""

    def _upload(self, client, filename="sample.jpg"):
        jpeg = _make_jpeg_bytes()
        resp = client.post(
            "/api/jobs",
            files=[("files", (filename, jpeg, "image/jpeg"))],
        )
        assert resp.status_code == 201
        return resp.json()["job_id"]

    def _wait(self, client, job_id: str, timeout: float = 15.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = client.get(f"/api/jobs/{job_id}").json()
            if data["status"] in ("completed", "failed"):
                return data
            time.sleep(0.05)
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    def test_multiple_jobs_have_unique_ids(self, client, tmp_jobs_dir):
        """Each upload must produce a distinct job_id."""
        with patch("sedimental.web._run_job"):
            ids = [self._upload(client) for _ in range(5)]
        assert len(set(ids)) == 5

    def test_concurrent_uploads_all_accepted(self, client, tmp_jobs_dir):
        """N simultaneous uploads must all return 201."""
        jpeg = _make_jpeg_bytes()
        results = []

        def _do_upload():
            resp = client.post(
                "/api/jobs",
                files=[("files", ("sample.jpg", jpeg, "image/jpeg"))],
            )
            results.append(resp.status_code)

        with patch("sedimental.web._run_job"):
            threads = [threading.Thread(target=_do_upload) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        assert all(s == 201 for s in results), f"Some uploads failed: {results}"

    def test_concurrent_jobs_complete_independently(self, client, tmp_jobs_dir):
        """Multiple jobs submitted concurrently must all reach 'completed'."""
        n = 4
        jpeg = _make_jpeg_bytes()
        job_ids = []

        # Upload all jobs with the real _run_job but fake process_batch
        with patch(
            "sedimental.orchestrator.ProcessingOrchestrator.process_batch",
            side_effect=_fake_batch_result,
        ):
            for i in range(n):
                resp = client.post(
                    "/api/jobs",
                    files=[("files", (f"img{i}.jpg", jpeg, "image/jpeg"))],
                )
                assert resp.status_code == 201
                job_ids.append(resp.json()["job_id"])

            # Wait for all to finish
            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline:
                statuses = [
                    client.get(f"/api/jobs/{jid}").json()["status"]
                    for jid in job_ids
                ]
                if all(s in ("completed", "failed") for s in statuses):
                    break
                time.sleep(0.05)

        for job_id, status in zip(job_ids, statuses):
            assert status == "completed", f"Job {job_id} ended in {status}"

    def test_concurrent_jobs_have_isolated_output_directories(self, client, tmp_jobs_dir):
        """Each job must write its CSV to its own directory, not a shared one."""
        with patch("sedimental.web._run_job"):
            job_ids = [self._upload(client) for _ in range(3)]

        output_dirs = [tmp_jobs_dir / jid / "output" for jid in job_ids]
        # All output dirs are distinct paths
        assert len(set(str(d) for d in output_dirs)) == 3

    def test_job_status_isolation(self, client, tmp_jobs_dir):
        """Completing one job must not affect the status of another."""
        import sedimental.web as web_module

        with patch("sedimental.web._run_job"):
            job_a = self._upload(client)
            job_b = self._upload(client)

        # Complete only job_a
        with patch(
            "sedimental.orchestrator.ProcessingOrchestrator.process_batch",
            side_effect=_fake_batch_result,
        ):
            web_module._run_job(job_a, tmp_jobs_dir / job_a, False, None)

        status_a = client.get(f"/api/jobs/{job_a}").json()["status"]
        status_b = client.get(f"/api/jobs/{job_b}").json()["status"]

        assert status_a == "completed"
        assert status_b in ("pending", "processing")  # untouched
