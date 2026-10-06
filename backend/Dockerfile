FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Pinned dependencies first (docs/PLAN.md §14.7 D3), so this layer is reused
# until the lockfile changes. The project itself isn't pip-installed: the app
# runs from /app, next to the migrations/ directory it applies at startup.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY app ./app
COPY migrations ./migrations

# Recorded on every persisted run as its app_version, so replay can tell when
# a run came from a different build. Late, so it doesn't invalidate the
# dependency layer.
ARG GIT_SHA=dev
ENV GIT_SHA=$GIT_SHA

RUN useradd --system --uid 10001 --no-create-home agentnet
USER agentnet

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"

# Hot reload is for development only: docker-compose.dev.yml adds it.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
