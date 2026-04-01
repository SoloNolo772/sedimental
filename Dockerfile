# =============================================================================
# Sedimental Analysis Tool - Dockerfile
# =============================================================================
# Single-stage build on CUDA 12.1 + cuDNN 8 (Ubuntu 22.04) so that the
# Python environment, CUDA libraries, and application all share the same base.
# =============================================================================

FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# Labels for image metadata
LABEL maintainer="Sedimental Team"
LABEL description="Sediment grain analysis tool with ImageGrains and PyImageJ"
LABEL version="1.0.0"

# Install system dependencies
# - python3.10 + pip: runtime and package management
# - build-essential / git: needed to compile some Python packages
# - OpenJDK 21 JDK: required for PyImageJ/ImageJ2
# - Maven: required for PyImageJ to download ImageJ2 JARs
# - libgl1 / libglib2.0-0 etc.: headless image processing support
# - curl: HTTP health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-venv \
    python3-pip \
    build-essential \
    git \
    curl \
    openjdk-21-jdk-headless \
    maven \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && python3.10 -m pip install --upgrade pip wheel setuptools

# Set JAVA_HOME for PyImageJ
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Set environment variables for headless operation
ENV DISPLAY=:0
ENV QT_QPA_PLATFORM=offscreen
ENV NAPARI_HEADLESS=1
ENV PYIMAGEJ_HEADLESS=1

# Marker so cli.py knows it is running inside the container
ENV SEDIMENTAL_INSIDE_CONTAINER=1

# Ensure /tmp has proper permissions for pip
RUN chmod 1777 /tmp

# Install Python dependencies
# Placed before copying app code to leverage Docker layer caching
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Create application directories
RUN mkdir -p /app /data/input /data/output /data/temp /data/jobs

# Pre-initialize PyImageJ to download ImageJ2 JARs from Maven Central.
# Placed BEFORE copying app code so code changes don't bust this slow cache layer.
RUN python -c "import imagej; ij = imagej.init(); print('ImageJ2 initialized:', ij.getVersion())" || true

# Set working directory
WORKDIR /app

# Copy application code
COPY sedimental/ /app/sedimental/
COPY tests/ /app/tests/
COPY entrypoint.sh /app/entrypoint.sh
COPY segment_image.py /app/segment_image.py
RUN chmod +x /app/entrypoint.sh

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash sedimental \
    && chown -R sedimental:sedimental /app /data

USER sedimental

# Expose web interface port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health 2>/dev/null || /app/entrypoint.sh health

# Default entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command
CMD ["web", "--port", "8080"]
