#!/bin/bash
# =============================================================================
# Sedimental Test Runner
# =============================================================================
# Convenience script to run tests inside Docker container
# =============================================================================

set -e

echo "Building Docker image..."
docker-compose build

echo ""
echo "Running tests inside container..."
docker-compose run --rm sedimental test tests/ -v --tb=long -vv "$@"

echo ""
echo "Tests complete!"
