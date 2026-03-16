# =============================================================================
# Sedimental Analysis Tool - Multi-stage Dockerfile
# =============================================================================
# Stage 1: Builder - Install build dependencies and compile requirements
# Stage 2: Runtime - Minimal image with only runtime dependencies
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder
# -----------------------------------------------------------------------------
FROM python:3.10-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for clean dependency isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip and install wheel
RUN pip install --no-cache-dir --upgrade pip wheel setuptools

# Ensure /tmp has proper permissions for pip
RUN chmod 1777 /tmp

# Install Python dependencies
# Note: We install these first to leverage Docker layer caching
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: Runtime
# -----------------------------------------------------------------------------
FROM python:3.10-slim AS runtime

# Labels for image metadata
LABEL maintainer="Sedimental Team"
LABEL description="Sediment grain analysis tool with ImageGrains and PyImageJ"
LABEL version="1.0.0"

# Install runtime dependencies
# - OpenJDK 21: Required for PyImageJ/ImageJ2 runtime (only version available in Debian Trixie)
# - Maven: Required for PyImageJ to download ImageJ2 components
# - libgl1: Required for headless image processing
# - libglib2.0-0: Required for various image libraries
# - curl: Required for HTTP health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jre-headless \
    maven \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libfontconfig1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set JAVA_HOME for PyImageJ
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set environment variables for headless operation
ENV DISPLAY=:0
ENV QT_QPA_PLATFORM=offscreen
ENV NAPARI_HEADLESS=1
ENV PYIMAGEJ_HEADLESS=1

# Create application directories
RUN mkdir -p /app /data/input /data/output /data/temp /data/jobs

# Set working directory
WORKDIR /app

# Copy application code
COPY sedimental/ /app/sedimental/
COPY tests/ /app/tests/
COPY entrypoint.sh /app/entrypoint.sh
COPY segment_image.py /app/segment_image.py
RUN chmod +x /app/entrypoint.sh

# Pre-initialize PyImageJ to download ImageJ2 components during build
# This avoids slow first-run initialization
RUN python -c "import imagej; ij = imagej.init(); print('ImageJ2 initialized:', ij.getVersion())" || true

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash sedimental \
    && chown -R sedimental:sedimental /app /data

USER sedimental

# Expose web interface port
EXPOSE 8080

# Health check endpoint - uses HTTP endpoint when web server is running
# Falls back to basic Python check for CLI-only containers
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health 2>/dev/null || /app/entrypoint.sh health

# Default entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command (can be overridden)
CMD ["web", "--port", "8080"]
