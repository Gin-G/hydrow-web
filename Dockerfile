# ── Stage 1: build dependencies ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim

# Non-root user for security
RUN addgroup --system hydrow && adduser --system --ingroup hydrow hydrow

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY wsgi.py .
COPY app/ ./app/

# Owned by non-root user
RUN chown -R hydrow:hydrow /app

USER hydrow

EXPOSE 8000

# Gunicorn: 2 workers per CPU core is a common starting point.
# WORKERS can be overridden via environment variable in your k8s manifest.
ENV WORKERS=2

CMD gunicorn \
    --bind 0.0.0.0:8000 \
    --workers ${WORKERS} \
    --worker-class sync \
    --timeout 30 \
    --access-logfile - \
    --error-logfile - \
    --log-level warning \
    wsgi:application