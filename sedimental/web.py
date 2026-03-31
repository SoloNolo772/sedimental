"""
Sedimental Web - FastAPI web interface for sediment analysis.

This module provides the web server for uploading images and downloading results,
including health check endpoints for container readiness verification and a
job-based processing API.
"""

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

logger = logging.getLogger("sedimental.web")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_FILE_SIZE_BYTES = int(os.environ.get("SEDIMENTAL_MAX_FILE_SIZE", str(50 * 1024 * 1024)))  # default 50 MB
JPEG_MAGIC_BYTES = b"\xff\xd8\xff"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
JOBS_DIR = Path(os.environ.get("SEDIMENTAL_JOBS_DIR", "/data/jobs"))
HEALTH_STATUS_FILE = Path("/tmp/sedimental_health_status")
DB_PATH = JOBS_DIR / "jobs.db"

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    """Open a SQLite connection with row_factory set."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the jobs table if it doesn't exist."""
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK (status IN ('pending','processing','completed','failed')),
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                input_files TEXT NOT NULL,
                metadata TEXT,
                save_masks INTEGER DEFAULT 0,
                result_path TEXT,
                error_message TEXT,
                progress_current INTEGER DEFAULT 0,
                progress_total INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)")
        conn.commit()


def _update_job(job_id: str, **kwargs) -> None:
    """Update arbitrary columns on a job row."""
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [job_id]
    with _get_db() as conn:
        conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)
        conn.commit()


def _get_job(job_id: str) -> Optional[sqlite3.Row]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------

def _run_job(job_id: str, job_dir: Path, save_masks: bool, metadata_dict: Optional[dict]) -> None:
    """Execute a processing job synchronously (runs in a thread)."""
    from .metadata import MetadataParser
    from .models import SampleMetadata
    from .orchestrator import ProcessingOrchestrator

    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        _update_job(job_id, status="processing")

        # Count images for progress tracking
        image_files = list(input_dir.glob("*.jpg")) + list(input_dir.glob("*.jpeg")) + \
                      list(input_dir.glob("*.JPG")) + list(input_dir.glob("*.JPEG"))
        _update_job(job_id, progress_total=len(image_files), progress_current=0)

        # Write metadata.json if provided
        meta_path: Optional[Path] = None
        if metadata_dict:
            meta_path = job_dir / "metadata.json"
            meta_path.write_text(json.dumps(metadata_dict))

        orchestrator = ProcessingOrchestrator()
        result_csv = output_dir / "results.csv"

        batch = orchestrator.process_batch(
            input_path=input_dir,
            output_path=result_csv,
            metadata_path=meta_path,
            save_masks=save_masks,
        )

        _update_job(
            job_id,
            status="completed",
            result_path=str(result_csv),
            progress_current=batch.successful,
            progress_total=batch.total_images,
        )
    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        _update_job(job_id, status="failed", error_message=str(exc))


async def _run_job_async(job_id: str, job_dir: Path, save_masks: bool, metadata_dict: Optional[dict]) -> None:
    """Run the blocking job in a thread pool so the event loop stays free."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_job, job_id, job_dir, save_masks, metadata_dict)


# ---------------------------------------------------------------------------
# Health helpers (preserved from original)
# ---------------------------------------------------------------------------

def check_core_libraries() -> dict:
    results = {}
    try:
        import numpy
        results["numpy"] = {"status": "ok", "version": numpy.__version__}
    except ImportError as e:
        results["numpy"] = {"status": "error", "error": str(e)}
    try:
        import PIL
        results["pillow"] = {"status": "ok", "version": PIL.__version__}
    except ImportError as e:
        results["pillow"] = {"status": "error", "error": str(e)}
    try:
        import skimage
        results["scikit-image"] = {"status": "ok", "version": skimage.__version__}
    except ImportError as e:
        results["scikit-image"] = {"status": "error", "error": str(e)}
    return results


def check_imagegrains() -> dict:
    try:
        import imagegrains
        return {"status": "ok", "version": getattr(imagegrains, "__version__", "unknown")}
    except ImportError as e:
        return {"status": "error", "error": str(e)}


def check_pyimagej() -> dict:
    try:
        import imagej  # noqa: F401
        return {"status": "ok", "note": "import successful, full init deferred"}
    except ImportError as e:
        return {"status": "error", "error": str(e)}


def check_napari() -> dict:
    try:
        os.environ["NAPARI_HEADLESS"] = "1"
        import napari
        return {"status": "ok", "version": napari.__version__}
    except ImportError as e:
        return {"status": "error", "error": str(e)}


def get_health_status() -> dict:
    status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "checks": {},
    }
    core = check_core_libraries()
    status["checks"]["core_libraries"] = core
    if any(v.get("status") == "error" for v in core.values()):
        status["status"] = "unhealthy"
    status["checks"]["imagegrains"] = check_imagegrains()
    if status["checks"]["imagegrains"]["status"] == "error":
        status["status"] = "degraded" if status["status"] == "healthy" else status["status"]
    status["checks"]["pyimagej"] = check_pyimagej()
    if status["checks"]["pyimagej"]["status"] == "error":
        status["status"] = "degraded" if status["status"] == "healthy" else status["status"]
    status["checks"]["napari"] = check_napari()
    if status["checks"]["napari"]["status"] == "error":
        status["status"] = "degraded" if status["status"] == "healthy" else status["status"]
    if HEALTH_STATUS_FILE.exists():
        try:
            status["init_status"] = json.loads(HEALTH_STATUS_FILE.read_text())
        except Exception:
            pass
    return status


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> "FastAPI":
    """Create and configure the FastAPI application."""
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI not available. Install with: pip install fastapi uvicorn")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        yield

    app = FastAPI(
        title="Sedimental API",
        description="Sediment grain analysis tool API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Health endpoints
    # ------------------------------------------------------------------

    @app.get("/health")
    async def health():
        """Basic health check — returns 200 if the service is running."""
        return {"status": "ok"}

    @app.get("/health/live")
    async def liveness():
        return {"status": "alive", "timestamp": datetime.utcnow().isoformat() + "Z"}

    @app.get("/health/ready")
    async def readiness():
        status = get_health_status()
        if status["status"] == "unhealthy":
            return JSONResponse(status_code=503, content=status)
        return status

    @app.get("/health/detailed")
    async def detailed_health():
        return get_health_status()

    @app.get("/")
    async def root():
        return {
            "name": "Sedimental API",
            "version": "1.0.0",
            "description": "Sediment grain analysis tool",
            "endpoints": {
                "health": "/health",
                "jobs": "/api/jobs",
            },
        }

    # ------------------------------------------------------------------
    # Job endpoints
    # ------------------------------------------------------------------

    @app.post("/api/jobs", status_code=201)
    async def create_job(
        files: List[UploadFile] = File(...),
        sample_id: Optional[str] = Form(None),
        location_lat: Optional[float] = Form(None),
        location_lon: Optional[float] = Form(None),
        location_description: Optional[str] = Form(None),
        capture_date: Optional[str] = Form(None),
        scale_ppm: Optional[float] = Form(None),
        submitted_by: Optional[str] = Form(None),
        save_masks: bool = Form(False),
    ):
        """
        Create a new processing job.

        Accepts one or more JPEG uploads plus optional metadata fields.
        Returns a job_id that can be polled via GET /api/jobs/{job_id}.
        """
        if not files:
            raise HTTPException(status_code=422, detail="At least one file is required")

        job_id = str(uuid.uuid4())
        job_dir = JOBS_DIR / job_id
        input_dir = job_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)

        # Validate and persist uploaded files
        filenames = []
        for upload in files:
            content = await upload.read()

            # Enforce maximum file size
            if len(content) > MAX_FILE_SIZE_BYTES:
                size_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
                size_str = f"{size_mb:.0f} MB" if size_mb >= 1 else f"{MAX_FILE_SIZE_BYTES} bytes"
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"File '{upload.filename}' exceeds the maximum allowed size of "
                        f"{size_str}."
                    ),
                )

            # Validate JPEG magic bytes
            if not content[:3] == JPEG_MAGIC_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"File '{upload.filename}' is not a valid JPEG image. "
                        "Only JPEG files are accepted."
                    ),
                )

            dest = input_dir / (upload.filename or f"upload_{uuid.uuid4().hex}.jpg")
            dest.write_bytes(content)
            filenames.append(dest.name)

        # Build metadata dict for the job
        metadata_dict: Optional[dict] = None
        default_meta: dict = {}
        if sample_id is not None:
            default_meta["sample_id"] = sample_id
        if location_lat is not None or location_lon is not None:
            default_meta["location"] = {
                k: v for k, v in [("lat", location_lat), ("lon", location_lon)] if v is not None
            }
        if location_description is not None:
            default_meta["location_description"] = location_description
        if capture_date is not None:
            default_meta["capture_date"] = capture_date
        if scale_ppm is not None:
            default_meta["scale_ppm"] = scale_ppm
        if submitted_by is not None:
            default_meta["submitted_by"] = submitted_by
        if default_meta:
            metadata_dict = {"default": default_meta, "images": {}}

        # Insert job record
        with _get_db() as conn:
            conn.execute(
                """INSERT INTO jobs (id, status, input_files, metadata, save_masks)
                   VALUES (?, 'pending', ?, ?, ?)""",
                (job_id, json.dumps(filenames), json.dumps(metadata_dict), int(save_masks)),
            )
            conn.commit()

        # Kick off background processing
        asyncio.create_task(_run_job_async(job_id, job_dir, save_masks, metadata_dict))

        return {"job_id": job_id, "status": "pending", "files": filenames}

    @app.get("/api/jobs/{job_id}")
    async def get_job_status(job_id: str):
        """Get the current status and progress of a processing job."""
        row = _get_job(job_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

        return {
            "job_id": row["id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "progress": {
                "current": row["progress_current"],
                "total": row["progress_total"],
            },
            "files": json.loads(row["input_files"]),
            "save_masks": bool(row["save_masks"]),
            "error_message": row["error_message"],
        }

    @app.get("/api/jobs/{job_id}/results")
    async def download_results(job_id: str):
        """Download the results CSV for a completed job."""
        row = _get_job(job_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
        if row["status"] != "completed":
            raise HTTPException(
                status_code=409,
                detail=f"Job is not completed (current status: {row['status']})",
            )
        result_path = row["result_path"]
        if not result_path or not Path(result_path).exists():
            raise HTTPException(status_code=404, detail="Result file not found")

        return FileResponse(
            path=result_path,
            media_type="text/csv",
            filename=f"results_{job_id}.csv",
        )

    @app.get("/api/jobs/{job_id}/masks/{filename}")
    async def download_mask(job_id: str, filename: str):
        """Download a segmentation mask TIFF for a completed job."""
        row = _get_job(job_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
        if row["status"] != "completed":
            raise HTTPException(
                status_code=409,
                detail=f"Job is not completed (current status: {row['status']})",
            )

        # Masks are written to <job_dir>/output/masks/
        mask_path = JOBS_DIR / job_id / "output" / "masks" / filename
        if not mask_path.exists():
            raise HTTPException(status_code=404, detail=f"Mask '{filename}' not found")

        return FileResponse(
            path=str(mask_path),
            media_type="image/tiff",
            filename=filename,
        )

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Entry point for sedimental web server."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Sedimental Web Server")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    args = parser.parse_args()

    if not FASTAPI_AVAILABLE:
        print("Error: FastAPI not available. Install with: pip install fastapi uvicorn")
        return 1

    print(f"Starting Sedimental web server on {args.host}:{args.port}")
    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
