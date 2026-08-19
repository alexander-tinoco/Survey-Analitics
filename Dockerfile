# Build stage — compile wheels once so the runtime image carries no toolchain.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /wheels

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
RUN pip wheel --wheel-dir /wheels -r requirements/dev.txt


# Runtime stage
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Run as an unprivileged user: a container breakout should not land on root.
RUN groupadd --system app && useradd --system --gid app --create-home app

# WORKDIR creates /app owned by root, and COPY --chown only sets ownership on
# the files it copies — not on the directory holding them. The application
# would then be unable to write anything beside its own source: ruff's cache,
# pytest's cache, a coverage report. Local development hid this, because the
# bind mount replaced /app with a directory the host user owns.
RUN mkdir -p /app && chown app:app /app
WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements/ requirements/
RUN pip install --no-index --find-links=/wheels -r requirements/dev.txt \
    && rm -rf /wheels

COPY --chown=app:app . .

USER app

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
