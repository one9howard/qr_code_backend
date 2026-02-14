FROM python:3.14.3-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PIP_DISABLE_PIP_VERSION_CHECK=1 \
  PIP_NO_CACHE_DIR=1 \
  PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN useradd -m insite

RUN apt-get update && apt-get install -y --no-install-recommends \
  curl build-essential gcc libpq-dev libzbar0 \
  libxrender1 libxext6 fontconfig \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY requirements-test.txt /app/requirements-test.txt

ARG INSTALL_DEV=false

RUN python -m pip install --upgrade pip setuptools wheel \
  && pip install -r /app/requirements.txt \
  && if [ "$INSTALL_DEV" = "true" ]; then \
  echo "Installing test dependencies..." \
  && pip install -r /app/requirements-test.txt \
  && mkdir -p ${PLAYWRIGHT_BROWSERS_PATH} \
  && python -m playwright install --with-deps chromium \
  && chown -R insite:insite ${PLAYWRIGHT_BROWSERS_PATH}; \
  else \
  echo "Skipping test dependencies (INSTALL_DEV=$INSTALL_DEV)"; \
  fi

COPY . /app
RUN chown -R insite:insite /app

RUN mkdir -p /var/lib/insite/uploads && chown -R insite:insite /var/lib/insite

USER insite

# informative only; Railway uses PORT env var
EXPOSE 8080

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]

# IMPORTANT: use exec and a PORT fallback for local runs
CMD ["sh", "-c", "echo '[Gunicorn] Starting on port: ${PORT:-8080}' && exec gunicorn --workers ${WEB_CONCURRENCY:-3} --bind 0.0.0.0:${PORT:-8080} --log-level info --access-logfile - --error-logfile - app:app"]

