# The identity_sync service with the project's token library.
#
# Build from the backend folder, because the library lives outside this folder:
#   docker build -f identity/identity_sync/Dockerfile -t fs-identity-sync .
#
# Every setting comes from the environment at run time. Nothing from `.env` is copied in.
# See `.env.example` for the names.

# python:3.14-slim-bookworm, pinned by digest (Python 3.14.10 on 22 November 2026).
FROM python@sha256:3fe1a0b6c2d6b2ebb572906cdabeca75aeb558c0c17db5ffefbcf8094871c32b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY libs/oidc_verify /src/oidc_verify
COPY identity/identity_sync/pyproject.toml /src/identity_sync/pyproject.toml
COPY identity/identity_sync/identity_sync /src/identity_sync/identity_sync

# Without oidc_verify the service refuses every endpoint that needs a service credential.
# The import check makes the build fail instead.
RUN pip install --no-cache-dir /src/oidc_verify /src/identity_sync \
    && python -c "import oidc_verify, identity_sync" \
    && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin identity \
    && mkdir /data \
    && chown identity /data

# The container listens on every interface. Publish the port on 127.0.0.1 only.
ENV IDENTITY_SYNC_HOST=0.0.0.0 \
    IDENTITY_SYNC_PORT=6115 \
    IDENTITY_SYNC_DB=/data/identity_sync.sqlite3

USER identity
VOLUME /data
EXPOSE 6115

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6115/healthz', timeout=3)"]

CMD ["python", "-m", "identity_sync", "serve"]
