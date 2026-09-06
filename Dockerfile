FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    ESKY_DATA_DIR=/data \
    ESKY_HOST=0.0.0.0 \
    ESKY_PORT=8080 \
    FASTEMBED_CACHE_PATH=/models

WORKDIR /app


# --- dev: editable install, source bind-mounted at run time ---------------
FROM base AS dev
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[dev]"
CMD ["pytest", "-v"]


# --- prod: immutable install with the ONNX model baked in -----------------
FROM base AS prod
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Pre-download the ONNX model so the first write is not a cold start.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

VOLUME ["/data"]
EXPOSE 8080
CMD ["esky", "serve"]
