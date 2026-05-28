# Stage 1: Build dependencies
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Install uv for faster package installation
RUN pip install --no-cache-dir uv

# Copy only requirements to leverage layer caching
COPY requirements.txt .

# Better approach - more aggressive cleanup
RUN uv pip install --system torch torchvision --extra-index-url https://download.pytorch.org/whl/cpu \
    && uv pip install --system --no-cache-dir -r requirements.txt \
    docling==2.60.1 \
    docling-ocr-onnxtr[cpu] \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    && uv cache clean \
    && pip cache purge \
    && rm -rf /root/.cache /tmp/* /var/tmp/* \
    && find /usr/local -name '*.pyc' -delete \
    && find /usr/local -name '__pycache__' -type d -exec rm -rf {} +

# Stage 2: Create backend-core image
FROM python:3.11-slim-bookworm AS backend-core

WORKDIR /app

# Set only essential Python environment variable
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Install system dependencies for OCR and clean up in one layer
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    poppler-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/artifacts/docling

# Copy application code (use .dockerignore to exclude unnecessary files)
COPY . .

# Run PyArmor to obfuscate modules within trial license limits (avoiding large files)
RUN pyarmor gen --recursive --output dist agents repository routes schemas utils workers && \
    cp -r /app/dist/* /app/ && rm -rf /app/dist

# Expose port 8000
EXPOSE 8000