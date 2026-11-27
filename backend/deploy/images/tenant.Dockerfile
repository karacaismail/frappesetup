# Production image of the tenant site: ERPNext, HRMS, platform_core and hrms_tr.
# Build context is the backend folder:
#   docker build -f deploy/images/tenant.Dockerfile .
# The image holds code and built assets only. Site data, site_config.json and secrets live in
# volumes and server files (docs/dagitim/ortamlar.md). The development image is dev/Dockerfile.tenant;
# this file keeps the same pinned base and HRMS commit, without test tools and the dev/ folder.
FROM frappe/erpnext:v16.55.0@sha256:15a1270f7d8d674de5facd16c3390665a12bd632f5abb846bdd67b61d7461d84
RUN git clone --depth 1 --branch v16.54.1 https://github.com/frappe/hrms.git apps/hrms \
    && test "$(git -C apps/hrms rev-parse HEAD)" = a01032350ba1b799345b862cb122fa408bf6780e \
    && rm -rf apps/hrms/.git \
    && (cd apps/hrms && yarn install --frozen-lockfile --non-interactive) \
    && uv pip install --python env/bin/python --no-deps -e apps/hrms \
    && uv pip check --python env/bin/python \
    && printf '\nhrms\n' >> sites/apps.txt
COPY --chown=1000:0 libs/oidc_verify /tmp/oidc_verify
# atonota_login decision code (G-161). Frappe imports the package; the code is not copied into the app.
COPY --chown=1000:0 identity/atonota_login /tmp/atonota_login
COPY --chown=1000:0 apps/platform_core /home/frappe/frappe-bench/apps/platform_core
COPY --chown=1000:0 apps/hrms_tr /home/frappe/frappe-bench/apps/hrms_tr
COPY --chown=1000:0 contracts/platform_core-ai.openapi.yaml contracts/platform_core-identity.openapi.yaml contracts/platform_core-access.openapi.yaml /home/frappe/frappe-bench/contracts/
COPY --chown=1000:0 contracts/platform_core-model-gateway.openapi.yaml /home/frappe/frappe-bench/apps/platform_core/contracts/
RUN uv pip install --python env/bin/python --no-deps -e apps/platform_core \
    && uv pip install --python env/bin/python --no-deps /tmp/oidc_verify \
    && uv pip install --python env/bin/python --no-deps /tmp/atonota_login \
    && uv pip install --python env/bin/python --no-deps -e apps/hrms_tr \
    && uv pip check --python env/bin/python \
    && rm -rf /tmp/oidc_verify /tmp/atonota_login \
    && printf '\nplatform_core\nhrms_tr\n' >> sites/apps.txt \
    && bench build --apps hrms,platform_core,hrms_tr
