# Production image of Press: Press v0.154.1 with the patch series in press-patches/, press_tr and
# oidc_verify. Build context is the backend folder:
#   docker build -f deploy/images/press.Dockerfile .
# The image holds code, locked Python packages and built assets only. Site data, site_config.json
# and secrets live in volumes and server files (docs/dagitim/ortamlar.md). The development image
# is dev/press/Dockerfile; its patch-py314.sh never enters this image (decision O-52).
# The base is the same pinned frappe/erpnext image as tenant.Dockerfile (Frappe 16, Python 3.14).

# dockerfile==3.2.0 (pinned by Press) has a linux-amd64 wheel but no linux-arm64 wheel. Its sdist
# needs Go 1.21 and a C compiler. This stage builds the arm64 wheel from the hash-checked sdist;
# on amd64 it does nothing. The compiler and Go stay in this stage.
# The sdist build fetches Go code with GO111MODULE=off, without a pinned version (review 1,
# finding 2). So the arm64 build runs only for a local trial with PRESS_LOCAL_ARM64_TRIAL=1.
# bin/build-release builds every release image for linux/amd64 and never sets this argument.
FROM frappe/erpnext:v16.55.0@sha256:15a1270f7d8d674de5facd16c3390665a12bd632f5abb846bdd67b61d7461d84 AS dockerfile-wheel
USER root
ARG TARGETARCH
ARG GO_VERSION=1.21.13
ARG PRESS_LOCAL_ARM64_TRIAL=0
RUN set -eu; mkdir -p /wheels; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    if [ "$arch" != arm64 ]; then exit 0; fi; \
    [ "$PRESS_LOCAL_ARM64_TRIAL" = 1 ] || { \
        echo "arm64 needs unpinned Go code; build for linux/amd64 (local trial: PRESS_LOCAL_ARM64_TRIAL=1)" >&2; \
        exit 1; }; \
    apt-get update; apt-get install -y --no-install-recommends gcc libc6-dev; \
    curl -fsSLo /tmp/go.tgz "https://go.dev/dl/go${GO_VERSION}.linux-arm64.tar.gz"; \
    echo "2ca2d70dc9c84feef959eb31f2a5aac33eefd8c97fe48f1548886d737bffabd4  /tmp/go.tgz" | sha256sum -c -; \
    tar -xzf /tmp/go.tgz -C /usr/local; \
    curl -fsSLo /tmp/dockerfile-3.2.0.tar.gz https://files.pythonhosted.org/packages/source/d/dockerfile/dockerfile-3.2.0.tar.gz; \
    echo "e13fd3768216a788189e0667521e1435a273a4129119a8453085d897fc34aac8  /tmp/dockerfile-3.2.0.tar.gz" | sha256sum -c -; \
    PATH="/usr/local/go/bin:$PATH" GO111MODULE=off uv build --wheel --out-dir /wheels /tmp/dockerfile-3.2.0.tar.gz

FROM frappe/erpnext:v16.55.0@sha256:15a1270f7d8d674de5facd16c3390665a12bd632f5abb846bdd67b61d7461d84 AS press
# uv keeps no download cache in the layers. An ARG reaches every RUN but not the final image.
ARG UV_NO_CACHE=1
ARG PRESS_TAG=v0.154.1
ARG PRESS_COMMIT=7a4384d5eec9f0f0dce4124e9dd48b106e51222f
ARG FRAPPE_MCP_COMMIT=b5c9730d18401c85d4b3ea68d20e2ba6f2bb7e7c

# Press source at the pinned commit, then the patch series. "git apply --check" runs before each
# patch; a patch that does not fit stops the build. No code changes in a running container.
COPY --chown=1000:0 deploy/images/press-patches /tmp/press-patches
RUN git clone --depth 1 --branch "$PRESS_TAG" https://github.com/frappe/press.git apps/press \
    && test "$(git -C apps/press rev-parse HEAD)" = "$PRESS_COMMIT" \
    && for patch in /tmp/press-patches/*.patch; do \
        git -C apps/press apply --check "$patch" && git -C apps/press apply "$patch" || exit 1; \
    done \
    && rm -rf apps/press/.git /tmp/press-patches

# Python packages from the hashed lock. Base image packages keep their versions (the lock was
# resolved with them as constraints). frappe-mcp comes from one Git commit with --no-deps.
COPY --chown=1000:0 deploy/images/press-requirements.lock.txt deploy/images/press-pip-check.allowed /tmp/press-deps/
COPY --from=dockerfile-wheel --chown=1000:0 /wheels /tmp/press-deps/wheels
RUN set -eu; lock=/tmp/press-deps/press-requirements.lock.txt; \
    if [ -n "$(ls /tmp/press-deps/wheels)" ]; then \
        uv pip install --python env/bin/python --no-deps /tmp/press-deps/wheels/dockerfile-3.2.0-*.whl; \
        awk '/^dockerfile==/{skip=1; next} skip && /^ /{next} {skip=0; print}' "$lock" > /tmp/press-deps/lock.txt; \
        lock=/tmp/press-deps/lock.txt; \
    fi; \
    uv pip install --python env/bin/python --no-deps --require-hashes -r "$lock"; \
    git init -q /tmp/frappe-mcp; \
    git -C /tmp/frappe-mcp fetch -q --depth 1 https://github.com/frappe/mcp "$FRAPPE_MCP_COMMIT"; \
    git -C /tmp/frappe-mcp checkout -q --detach FETCH_HEAD; \
    test "$(git -C /tmp/frappe-mcp rev-parse HEAD)" = "$FRAPPE_MCP_COMMIT"; \
    uv pip install --python env/bin/python --no-deps /tmp/frappe-mcp; \
    uv pip install --python env/bin/python --no-deps -e apps/press; \
    rm -rf /tmp/frappe-mcp /tmp/press-deps/wheels "/tmp/press-deps/lock.txt"

COPY --chown=1000:0 libs/oidc_verify /tmp/oidc_verify
COPY --chown=1000:0 apps/press_tr /home/frappe/frappe-bench/apps/press_tr
# "uv pip check" must report exactly the lines in press-pip-check.allowed (each one is explained
# there). Any other mismatch, and any missing line, stops the build.
RUN set -eu; \
    uv pip install --python env/bin/python --no-deps /tmp/oidc_verify; \
    uv pip install --python env/bin/python --no-deps -e apps/press_tr; \
    rm -rf /tmp/oidc_verify; \
    { uv pip check --python env/bin/python 2>&1 || true; } | grep '^The package' | sort > /tmp/press-deps/pip-check.txt; \
    grep -v '^#' /tmp/press-deps/press-pip-check.allowed | sort | diff -u - /tmp/press-deps/pip-check.txt; \
    rm -rf /tmp/press-deps; \
    printf '\npress\npress_tr\n' >> sites/apps.txt

# Built assets. The base entrypoint.sh replaces sites/assets with a link to the baked folder
# /home/frappe/frappe-bench/assets at every start, so the build writes into that folder.
# The dashboard lock is installed first, so the root postinstall finds it complete.
# "bench build" would load the hooks of every built app after bundling. Press's hooks.py reads the
# database at import (press/api/account.py get_frappe_io_auth_url), and the build has no site.
# No app declares after_build or after_app_build (the grep below fails the build if one does),
# so the same two steps of "bench build" run here directly: bundle and compile translations.
# The desk bundles of frappe and erpnext must stay in assets.json next to the Press bundle.
# The dashboard build reads socketio_port from common_site_config.json (dashboard/src/socket.js);
# 9000 is the port of the press-socket service. It holds no secret.
# node_modules are build tools only and leave the image after the build.
RUN ln -s ../assets sites/assets \
    && bench set-config -gp socketio_port 9000 \
    && (cd apps/press/dashboard && yarn install --frozen-lockfile --non-interactive) \
    && (cd apps/press && yarn install --frozen-lockfile --non-interactive) \
    && ! grep -lE '^[[:space:]]*after_(app_)?build[[:space:]]*(\+?=|:)' apps/*/*/hooks.py \
    && cd sites \
    && /home/frappe/frappe-bench/env/bin/python -c "import frappe, frappe.commands; frappe.init(''); \
from frappe.bundler import bundle; bundle('production', apps='press,press_tr'); \
from frappe.gettext.translate import compile_translations; \
[compile_translations(app) for app in ('press', 'press_tr')]" \
    && cd .. \
    && test -f apps/press/press/public/dashboard/index.html \
    && python3 -c "import json, sys; bundles = json.load(open('assets/assets.json')); \
sys.exit(not all(name in bundles for name in ('desk.bundle.js', 'erpnext.bundle.js', 'press.bundle.js')))" \
    && rm -rf apps/press/node_modules apps/press/dashboard/node_modules \
    && yarn cache clean

# The base image entry stays: entrypoint.sh links the baked assets, start.sh runs gunicorn on 8000.
