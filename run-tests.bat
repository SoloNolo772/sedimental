@echo off
REM =============================================================================
REM Sedimental Test Runner (Windows)
REM =============================================================================
REM Convenience script to run tests inside Docker container
REM =============================================================================

echo Building Docker image...
docker-compose build

echo.
echo Running tests inside container...
docker-compose run --rm sedimental test tests/ -v --tb=short %*

echo.
echo Tests complete!
