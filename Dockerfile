FROM python:3.13-slim

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  FLASK_ENV=production \
  PORT=8080

WORKDIR /app

# System dependencies:
# - curl: for HEALTHCHECK
# - build-essential, gcc: for compiling some python deps
# - libpq-dev: for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
  curl build-essential gcc libpq-dev libzbar0 \
  libxrender1 libxext6 fontconfig \
  && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
# Copy test requirements but don't force install yet
COPY requirements-test.txt /app/requirements-test.txt

ARG INSTALL_DEV=false
RUN pip install --no-cache-dir -r /app/requirements.txt

# Use single line if/else to avoid potential EOL issues and keep it robust
RUN if [ "$INSTALL_DEV" = "true" ]; then echo "Installing test dependencies..." && pip install --no-cache-dir -r /app/requirements-test.txt; else echo "Skipping test dependencies (INSTALL_DEV=$INSTALL_DEV)"; fi

# Create non-root user
RUN useradd -m qrapp

# Copy application code
COPY . /app
RUN chown -R qrapp:qrapp /app

# Set up ENTRYPOINT script
COPY scripts/docker-entrypoint.sh /app/scripts/docker-entrypoint.sh
RUN chmod +x /app/scripts/docker-entrypoint.sh

# Create the persistent data directories & set ownership
# We default to /var/lib/qrapp matching config expectations
RUN mkdir -p /var/lib/qrapp/uploads && chown -R qrapp:qrapp /var/lib/qrapp

# Switch to non-root user
USER qrapp

# Expose the port (informative, but used by some tools)
EXPOSE 8080

# Health check - Disabled for Railway (uses its own health check system)
# HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
#   CMD curl -f http://127.0.0.1:${PORT}/ping || exit 1

# Entrypoint ensures migrations run
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]

# Default command: run Gunicorn
# Binds to 0.0.0.0 and PORT env var
CMD ["sh", "-c", "echo '[Gunicorn] Starting on port: $PORT' && gunicorn --workers 3 --bind 0.0.0.0:${PORT} --log-level debug --access-logfile - --error-logfile - app:app"]
