#!/bin/bash
# =============================================================================
# Sedimental Container Entrypoint Script
# =============================================================================
# Handles container startup, initialization verification, and command routing
# =============================================================================

set -e

# -----------------------------------------------------------------------------
# Environment Setup
# -----------------------------------------------------------------------------
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Health status file for tracking initialization state
HEALTH_STATUS_FILE="/tmp/sedimental_health_status"

# -----------------------------------------------------------------------------
# Initialization Verification
# -----------------------------------------------------------------------------
verify_imagegrains() {
    echo "[INIT] Verifying ImageGrains installation..."
    python -c "
import imagegrains
print('ImageGrains version:', getattr(imagegrains, '__version__', 'unknown'))
# Verify core functionality is accessible
from imagegrains import grainsizing
print('ImageGrains grainsizing module loaded')
" 2>/dev/null && {
        echo "[INIT] ImageGrains verification passed"
        return 0
    } || {
        echo "[WARN] ImageGrains import check failed, but continuing..."
        return 1
    }
}

verify_pyimagej() {
    echo "[INIT] Verifying PyImageJ installation..."
    python -c "
import imagej
print('PyImageJ available')
# Note: Full initialization is expensive, just verify import works
print('PyImageJ module loaded successfully')
" 2>/dev/null && {
        echo "[INIT] PyImageJ verification passed"
        return 0
    } || {
        echo "[WARN] PyImageJ import check failed, but continuing..."
        return 1
    }
}

verify_napari() {
    echo "[INIT] Verifying Napari (headless) installation..."
    python -c "
import os
os.environ['NAPARI_HEADLESS'] = '1'
import napari
print('Napari version:', napari.__version__)
" 2>/dev/null && {
        echo "[INIT] Napari verification passed"
        return 0
    } || {
        echo "[WARN] Napari import check failed, but continuing..."
        return 1
    }
}

# -----------------------------------------------------------------------------
# Full Initialization Check (for health endpoint)
# -----------------------------------------------------------------------------
run_full_init_check() {
    echo "[INIT] Running full initialization check..."
    
    local status="healthy"
    local checks_passed=0
    local checks_total=4
    
    # Check 1: Core Python libraries
    echo "[INIT] Checking core libraries..."
    python -c "
import numpy
import PIL
import skimage
import tifffile
print('Core libraries OK')
" && ((checks_passed++)) || status="degraded"
    
    # Check 2: ImageGrains
    verify_imagegrains && ((checks_passed++)) || status="degraded"
    
    # Check 3: PyImageJ
    verify_pyimagej && ((checks_passed++)) || status="degraded"
    
    # Check 4: Napari
    verify_napari && ((checks_passed++)) || status="degraded"
    
    # Write status file
    echo "{\"status\": \"$status\", \"checks_passed\": $checks_passed, \"checks_total\": $checks_total, \"timestamp\": \"$(date -Iseconds)\"}" > "$HEALTH_STATUS_FILE"
    
    echo "[INIT] Initialization check complete: $checks_passed/$checks_total checks passed (status: $status)"
    
    if [ "$status" = "healthy" ]; then
        return 0
    else
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Health Check Function
# -----------------------------------------------------------------------------
health_check() {
    echo "[HEALTH] Running health check..."
    
    # Check Python environment
    python --version || {
        echo "[HEALTH] Python not available"
        exit 1
    }
    
    # Check critical imports
    python -c "
import sys
import json

# Core library check
try:
    import numpy
    import PIL
    import skimage
except ImportError as e:
    print(f'[HEALTH] Core library import failed: {e}')
    sys.exit(1)

# Check if status file exists and read it
status_file = '/tmp/sedimental_health_status'
try:
    with open(status_file, 'r') as f:
        status = json.load(f)
        print(f'[HEALTH] Status: {status[\"status\"]}')
        print(f'[HEALTH] Checks: {status[\"checks_passed\"]}/{status[\"checks_total\"]}')
        if status['status'] == 'healthy':
            sys.exit(0)
        else:
            # Degraded but functional
            sys.exit(0)
except FileNotFoundError:
    print('[HEALTH] Status file not found, running basic check')
    # Basic check passed if we got here
    sys.exit(0)
except Exception as e:
    print(f'[HEALTH] Error reading status: {e}')
    sys.exit(1)
"
    
    echo "[HEALTH] Health check passed"
    exit 0
}

# -----------------------------------------------------------------------------
# Readiness Check (more thorough than health check)
# -----------------------------------------------------------------------------
readiness_check() {
    echo "[READY] Running readiness check..."
    
    # Run full initialization check
    run_full_init_check
    local init_status=$?
    
    # Check data directories are accessible
    python -c "
import os
import sys

dirs_to_check = ['/data/input', '/data/output', '/data/temp', '/data/jobs']
for d in dirs_to_check:
    if not os.path.isdir(d):
        print(f'[READY] Directory not found: {d}')
        sys.exit(1)
    if d != '/data/input' and not os.access(d, os.W_OK):
        print(f'[READY] Directory not writable: {d}')
        sys.exit(1)

print('[READY] All data directories accessible')
"
    
    if [ $init_status -eq 0 ]; then
        echo "[READY] Readiness check passed"
        exit 0
    else
        echo "[READY] Readiness check passed with warnings (degraded mode)"
        exit 0
    fi
}

# -----------------------------------------------------------------------------
# Command Routing
# -----------------------------------------------------------------------------
case "${1:-}" in
    health)
        health_check
        ;;
    ready|readiness)
        readiness_check
        ;;
    init-check)
        # Run initialization check and exit
        run_full_init_check
        exit $?
        ;;
    web)
        shift
        echo "[START] Starting web server..."
        # Run initialization check in background, don't block startup
        run_full_init_check &
        exec python -m sedimental.web "$@"
        ;;
    process)
        shift
        echo "[START] Running processing pipeline..."
        verify_imagegrains
        verify_pyimagej
        exec python -m sedimental.cli process "$@"
        ;;
    test)
        shift
        echo "[START] Running test suite..."
        # Run pytest with all arguments passed through
        exec python -m pytest "$@"
        ;;
    shell)
        echo "[START] Starting interactive shell..."
        exec /bin/bash
        ;;
    *)
        # Default: pass all arguments to the CLI
        echo "[START] Running sedimental CLI..."
        exec python -m sedimental.cli "$@"
        ;;
esac
