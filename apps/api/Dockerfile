# Production image for the FastAPI app. The worker uses the same deps but a different
# CMD — see Dockerfile.worker — kept separate so each image's purpose is explicit in
# its own file rather than branching on a build arg.
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN uv sync --locked --no-dev

EXPOSE 8000
# --no-sync: the image is already synced (--no-dev above); without this, `uv run`
# re-checks/re-syncs at every container start, which pulls dev deps back in and adds
# a multi-second delay before the app even starts.
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
