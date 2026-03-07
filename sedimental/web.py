"""
Sedimental Web - FastAPI web interface for sediment analysis.

This module provides the web server for uploading images and downloading results,
including health check endpoints for container readiness verification.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


# Health status file path (shared with entrypoint.sh)
HEALTH_STATUS_FILE = Path("/tmp/sedimental_health_status")


def check_core_libraries() -> dict:
    """Check if core libraries are importable."""
    results = {}
    
    # Core libraries
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
    """Check ImageGrains availability."""
    try:
        import imagegrains
        version = getattr(imagegrains, '__version__', 'unknown')
        return {"status": "ok", "version": version}
    except ImportError as e:
        return {"status": "error", "error": str(e)}


def check_pyimagej() -> dict:
    """Check PyImageJ availability (import only, not full init)."""
    try:
        import imagej
        return {"status": "ok", "note": "import successful, full init deferred"}
    except ImportError as e:
        return {"status": "error", "error": str(e)}


def check_napari() -> dict:
    """Check Napari availability in headless mode."""
    try:
        os.environ['NAPARI_HEADLESS'] = '1'
        import napari
        return {"status": "ok", "version": napari.__version__}
    except ImportError as e:
        return {"status": "error", "error": str(e)}


def get_health_status() -> dict:
    """Get comprehensive health status."""
    status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "checks": {}
    }
    
    # Check core libraries
    core = check_core_libraries()
    status["checks"]["core_libraries"] = core
    if any(v.get("status") == "error" for v in core.values()):
        status["status"] = "unhealthy"
    
    # Check ImageGrains
    status["checks"]["imagegrains"] = check_imagegrains()
    if status["checks"]["imagegrains"]["status"] == "error":
        status["status"] = "degraded" if status["status"] == "healthy" else status["status"]
    
    # Check PyImageJ
    status["checks"]["pyimagej"] = check_pyimagej()
    if status["checks"]["pyimagej"]["status"] == "error":
        status["status"] = "degraded" if status["status"] == "healthy" else status["status"]
    
    # Check Napari
    status["checks"]["napari"] = check_napari()
    if status["checks"]["napari"]["status"] == "error":
        status["status"] = "degraded" if status["status"] == "healthy" else status["status"]
    
    # Read cached status from entrypoint if available
    if HEALTH_STATUS_FILE.exists():
        try:
            with open(HEALTH_STATUS_FILE) as f:
                cached = json.load(f)
                status["init_status"] = cached
        except Exception:
            pass
    
    return status


def create_app() -> "FastAPI":
    """Create and configure the FastAPI application."""
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI not available. Install with: pip install fastapi uvicorn")
    
    app = FastAPI(
        title="Sedimental API",
        description="Sediment grain analysis tool API",
        version="1.0.0"
    )
    
    @app.get("/health")
    async def health():
        """
        Basic health check endpoint.
        
        Returns 200 if the service is running.
        Used by Docker HEALTHCHECK and load balancers.
        """
        return {"status": "ok"}
    
    @app.get("/health/live")
    async def liveness():
        """
        Liveness probe endpoint.
        
        Returns 200 if the process is alive.
        Kubernetes liveness probe compatible.
        """
        return {"status": "alive", "timestamp": datetime.utcnow().isoformat() + "Z"}
    
    @app.get("/health/ready")
    async def readiness():
        """
        Readiness probe endpoint.
        
        Returns detailed health status including dependency checks.
        Kubernetes readiness probe compatible.
        """
        status = get_health_status()
        
        # Return 503 if unhealthy (core libraries missing)
        if status["status"] == "unhealthy":
            return JSONResponse(status_code=503, content=status)
        
        # Return 200 for healthy or degraded (can still process, just with limitations)
        return status
    
    @app.get("/health/detailed")
    async def detailed_health():
        """
        Detailed health check with all component statuses.
        
        Returns comprehensive information about all dependencies.
        """
        return get_health_status()
    
    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "Sedimental API",
            "version": "1.0.0",
            "description": "Sediment grain analysis tool",
            "endpoints": {
                "health": "/health",
                "liveness": "/health/live",
                "readiness": "/health/ready",
                "detailed_health": "/health/detailed"
            }
        }
    
    return app


def main():
    """Entry point for sedimental web server."""
    parser = argparse.ArgumentParser(
        description='Sedimental Web Server'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8080,
        help='Port for web server (default: 8080)'
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )

    args = parser.parse_args()

    if not FASTAPI_AVAILABLE:
        print("Error: FastAPI not available. Install with: pip install fastapi uvicorn")
        return 1

    print(f"Starting Sedimental web server on {args.host}:{args.port}")
    
    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
