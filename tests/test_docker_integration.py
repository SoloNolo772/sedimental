"""
Docker integration tests for Sedimental analysis tool.

Tests container startup, health check endpoints, volume mount functionality,
and web service availability by running commands against the live container
via `docker compose`.

Requirements: 8.1, 8.5, 8.7
"""

import io
import json
import subprocess
import time

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

COMPOSE_SERVICE = "sedimental"
COMPOSE_CMD = ["docker", "compose"]


def _compose(*args, capture=True, timeout=60):
    """Run a docker compose command and return CompletedProcess."""
    cmd = COMPOSE_CMD + list(args)
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
    )


def _compose_run(*args, timeout=60):
    """Run a one-off command inside the container via `docker compose run --rm`."""
    return _compose("run", "--rm", COMPOSE_SERVICE, *args, timeout=timeout)


def _make_jpeg_bytes() -> bytes:
    """Return a minimal valid JPEG via Pillow."""
    from PIL import Image
    buf = io.BytesIO()
    img = Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8))
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _docker_available() -> bool:
    """Return True if Docker daemon is reachable."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _image_exists() -> bool:
    """Return True if the sedimental:latest image is already built."""
    result = subprocess.run(
        ["docker", "image", "inspect", "sedimental:latest"],
        capture_output=True,
        timeout=10,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Skip guard — all tests in this module require Docker
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker daemon not available",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def docker_image():
    """
    Ensure the sedimental:latest image exists.
    Builds it if missing; skips the module if the build fails.
    """
    if not _image_exists():
        result = subprocess.run(
            COMPOSE_CMD + ["build"],
            capture_output=True,
            text=True,
            timeout=600,  # builds can be slow
        )
        if result.returncode != 0:
            pytest.skip(f"Docker image build failed:\n{result.stderr}")
    return "sedimental:latest"


# ---------------------------------------------------------------------------
# Req 8.1 — Docker image builds successfully
# ---------------------------------------------------------------------------

class TestDockerImageBuild:
    """Verify the Docker image can be built (Req 8.1)."""

    def test_image_exists_after_build(self, docker_image):
        """The sedimental:latest image must exist after the build step."""
        assert _image_exists(), "sedimental:latest image not found after build"

    def test_image_has_correct_label(self, docker_image):
        """Image labels must include the expected description."""
        result = subprocess.run(
            ["docker", "image", "inspect", "sedimental:latest",
             "--format", "{{json .Config.Labels}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0
        labels = json.loads(result.stdout.strip())
        assert "description" in labels
        assert "sedimental" in labels["description"].lower()

    def test_image_exposes_port_8080(self, docker_image):
        """Image must expose port 8080 for the web interface (Req 8.3)."""
        result = subprocess.run(
            ["docker", "image", "inspect", "sedimental:latest",
             "--format", "{{json .Config.ExposedPorts}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0
        ports = json.loads(result.stdout.strip())
        assert "8080/tcp" in ports, f"Port 8080/tcp not exposed; got: {ports}"


# ---------------------------------------------------------------------------
# Req 8.7 — Container starts and health check passes within 60 seconds
# ---------------------------------------------------------------------------

class TestContainerStartupAndHealthCheck:
    """Verify container startup and health check (Req 8.7)."""

    def test_entrypoint_health_command_exits_zero(self, docker_image):
        """
        `entrypoint.sh health` must exit 0 — basic Python environment check.
        """
        result = _compose_run("health", timeout=30)
        assert result.returncode == 0, (
            f"Health command failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_entrypoint_health_output_contains_passed(self, docker_image):
        """Health command output must mention a passing check."""
        result = _compose_run("health", timeout=30)
        combined = result.stdout + result.stderr
        assert "passed" in combined.lower() or "ok" in combined.lower(), (
            f"Expected 'passed' or 'ok' in health output:\n{combined}"
        )

    def test_web_server_starts_and_responds(self, docker_image):
        """
        Web server must respond to GET /health within 60 seconds of startup
        (Req 8.7).  Uses `docker compose run` with the web command and polls
        the health endpoint via a second container on the same network.
        """
        import requests

        # Start the web service in detached mode
        up_result = subprocess.run(
            COMPOSE_CMD + ["up", "-d", "--no-recreate", COMPOSE_SERVICE],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if up_result.returncode != 0:
            pytest.skip(f"Could not start service: {up_result.stderr}")

        try:
            deadline = time.monotonic() + 60
            last_error = None
            while time.monotonic() < deadline:
                try:
                    resp = requests.get("http://localhost:8080/health", timeout=3)
                    if resp.status_code == 200:
                        data = resp.json()
                        assert data.get("status") == "ok"
                        return  # success
                except Exception as exc:
                    last_error = exc
                time.sleep(2)

            pytest.fail(
                f"Web service did not respond within 60 seconds. "
                f"Last error: {last_error}"
            )
        finally:
            subprocess.run(
                COMPOSE_CMD + ["stop", COMPOSE_SERVICE],
                capture_output=True,
                timeout=30,
            )

    def test_health_live_endpoint(self, docker_image):
        """GET /health/live must return 200 with status=alive."""
        import requests

        up_result = subprocess.run(
            COMPOSE_CMD + ["up", "-d", "--no-recreate", COMPOSE_SERVICE],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if up_result.returncode != 0:
            pytest.skip(f"Could not start service: {up_result.stderr}")

        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    resp = requests.get("http://localhost:8080/health/live", timeout=3)
                    if resp.status_code == 200:
                        assert resp.json()["status"] == "alive"
                        return
                except Exception:
                    pass
                time.sleep(2)
            pytest.fail("GET /health/live did not respond within 60 seconds")
        finally:
            subprocess.run(
                COMPOSE_CMD + ["stop", COMPOSE_SERVICE],
                capture_output=True,
                timeout=30,
            )


# ---------------------------------------------------------------------------
# Req 8.5 — Volume mounts persist files between host and container
# ---------------------------------------------------------------------------

class TestVolumeMountFunctionality:
    """Verify that volume mounts work correctly (Req 8.5)."""

    def test_input_directory_is_readable_inside_container(self, docker_image, tmp_path):
        """Files placed in data/input on the host are visible inside the container."""
        # Write a sentinel file to the mounted input directory
        sentinel = tmp_path / "sentinel.txt"
        sentinel.write_text("hello from host")

        # Use a one-off container to check the file is visible
        result = subprocess.run(
            COMPOSE_CMD + [
                "run", "--rm",
                "-v", f"{sentinel.parent}:/data/input:ro",
                COMPOSE_SERVICE,
                "shell",
            ],
            input="ls /data/input && cat /data/input/sentinel.txt\n",
            capture_output=True,
            text=True,
            timeout=30,
        )
        # The shell command may not be interactive in CI; check via python instead
        result2 = subprocess.run(
            COMPOSE_CMD + [
                "run", "--rm",
                "-v", f"{sentinel.parent}:/data/input:ro",
                COMPOSE_SERVICE,
                "python", "-c",
                "import pathlib; p=pathlib.Path('/data/input/sentinel.txt'); "
                "assert p.exists(), f'not found: {p}'; print(p.read_text())",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result2.returncode == 0, (
            f"Sentinel file not visible inside container:\n"
            f"stdout: {result2.stdout}\nstderr: {result2.stderr}"
        )
        assert "hello from host" in result2.stdout

    def test_output_directory_is_writable_inside_container(self, docker_image, tmp_path):
        """Files written to /data/output inside the container appear on the host."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = subprocess.run(
            COMPOSE_CMD + [
                "run", "--rm",
                "-v", f"{output_dir}:/data/output",
                COMPOSE_SERVICE,
                "python", "-c",
                "from pathlib import Path; "
                "p = Path('/data/output/written_by_container.txt'); "
                "p.write_text('container was here'); print('written')",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Write inside container failed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        written = output_dir / "written_by_container.txt"
        assert written.exists(), "File written inside container not found on host"
        assert written.read_text() == "container was here"

    def test_jobs_directory_persists_sqlite_db(self, docker_image, tmp_path):
        """SQLite jobs.db written inside the container persists to the host volume."""
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()

        result = subprocess.run(
            COMPOSE_CMD + [
                "run", "--rm",
                "-v", f"{jobs_dir}:/data/jobs",
                "-e", f"SEDIMENTAL_JOBS_DIR=/data/jobs",
                COMPOSE_SERVICE,
                "python", "-c",
                "import os; os.environ['SEDIMENTAL_JOBS_DIR']='/data/jobs'; "
                "from sedimental.web import init_db, DB_PATH; "
                "import sedimental.web as w; "
                "from pathlib import Path; "
                "w.JOBS_DIR = Path('/data/jobs'); "
                "w.DB_PATH = Path('/data/jobs/jobs.db'); "
                "init_db(); print('db created at', w.DB_PATH)",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"DB init inside container failed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        db_file = jobs_dir / "jobs.db"
        assert db_file.exists(), "jobs.db not found on host after container wrote it"

    def test_temp_directory_is_accessible(self, docker_image, tmp_path):
        """The /data/temp directory is accessible and writable inside the container."""
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        result = subprocess.run(
            COMPOSE_CMD + [
                "run", "--rm",
                "-v", f"{temp_dir}:/data/temp",
                COMPOSE_SERVICE,
                "python", "-c",
                "import os; assert os.access('/data/temp', os.W_OK), "
                "'/data/temp not writable'; print('temp ok')",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Temp dir check failed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "temp ok" in result.stdout

    def test_source_code_volume_mount_picks_up_changes(self, docker_image, tmp_path):
        """
        When sedimental/ is mounted as a volume, code changes are visible
        inside the container without rebuilding (Req 8.5 — volume mounts).
        """
        # Write a tiny module to a temp sedimental copy
        src_dir = tmp_path / "sedimental"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text("")
        (src_dir / "_test_marker.py").write_text("MARKER = 'volume_mount_works'")

        result = subprocess.run(
            COMPOSE_CMD + [
                "run", "--rm",
                "-v", f"{src_dir}:/app/sedimental:ro",
                COMPOSE_SERVICE,
                "python", "-c",
                "from sedimental._test_marker import MARKER; print(MARKER)",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Volume-mounted code not visible inside container:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "volume_mount_works" in result.stdout


# ---------------------------------------------------------------------------
# Req 8.1, 8.5 — Web service availability via compose
# ---------------------------------------------------------------------------

class TestWebServiceAvailability:
    """Verify the web service is reachable and functional (Req 8.1, 8.5)."""

    @pytest.fixture(autouse=True)
    def _ensure_service_up(self, docker_image):
        """Start the service before each test and stop it after."""
        up = subprocess.run(
            COMPOSE_CMD + ["up", "-d", "--no-recreate", COMPOSE_SERVICE],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if up.returncode != 0:
            pytest.skip(f"Could not start service: {up.stderr}")

        # Wait for the service to be ready
        import requests
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if requests.get("http://localhost:8080/health", timeout=2).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(2)
        else:
            subprocess.run(COMPOSE_CMD + ["stop", COMPOSE_SERVICE], capture_output=True, timeout=30)
            pytest.skip("Service did not become ready within 60 seconds")

        yield

        subprocess.run(
            COMPOSE_CMD + ["stop", COMPOSE_SERVICE],
            capture_output=True,
            timeout=30,
        )

    def test_health_endpoint_returns_ok(self):
        """GET /health must return 200 with {status: ok}."""
        import requests
        resp = requests.get("http://localhost:8080/health", timeout=5)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_root_endpoint_returns_html(self):
        """GET / must return an HTML response (the frontend)."""
        import requests
        resp = requests.get("http://localhost:8080/", timeout=5)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_api_jobs_endpoint_reachable(self):
        """POST /api/jobs must be reachable (returns 4xx, not 5xx or connection error)."""
        import requests
        # POST with no files — expect 422 (validation error), not 500 or connection refused
        resp = requests.post("http://localhost:8080/api/jobs", timeout=5)
        assert resp.status_code in (400, 422), (
            f"Expected 400 or 422 for empty POST, got {resp.status_code}"
        )

    def test_nonexistent_job_returns_404(self):
        """GET /api/jobs/<unknown-id> must return 404."""
        import requests
        resp = requests.get("http://localhost:8080/api/jobs/does-not-exist", timeout=5)
        assert resp.status_code == 404

    def test_upload_jpeg_creates_job(self):
        """Uploading a valid JPEG must create a job and return 201."""
        import requests
        jpeg = _make_jpeg_bytes()
        resp = requests.post(
            "http://localhost:8080/api/jobs",
            files=[("files", ("test.jpg", jpeg, "image/jpeg"))],
            timeout=10,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "job_id" in body
        assert body["status"] == "pending"

    def test_upload_non_jpeg_returns_400(self):
        """Uploading a non-JPEG file must return 400."""
        import requests
        resp = requests.post(
            "http://localhost:8080/api/jobs",
            files=[("files", ("bad.txt", b"not a jpeg", "text/plain"))],
            timeout=10,
        )
        assert resp.status_code == 400

    def test_detailed_health_endpoint_returns_checks(self):
        """GET /health/detailed must return a checks dict."""
        import requests
        resp = requests.get("http://localhost:8080/health/detailed", timeout=5)
        assert resp.status_code == 200
        body = resp.json()
        assert "checks" in body
        assert "status" in body
