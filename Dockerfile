# ── Build stage ──────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────
FROM python:3.11-slim

# Create a non-root user (required for OpenShift which runs as an
# arbitrary UID in the range 1000-65535).
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /sbin/nologin -d /app appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Optional: pre-bake a config file at the standard path.
# Users can also mount a ConfigMap / Secret to /etc/vault-demo/config.yaml
RUN mkdir -p /etc/vault-demo

# Give the arbitrary OpenShift UID write access to nothing sensitive –
# the app itself is read-only; only log output goes to stdout.
RUN chown -R 1001:0 /app /etc/vault-demo && chmod -R g=u /app /etc/vault-demo

USER 1001

WORKDIR /app/backend

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1

# Use gunicorn for production; fall back to Flask dev server via env flag.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--threads", "4", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
