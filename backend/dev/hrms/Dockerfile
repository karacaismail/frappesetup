ARG KIRACI_IMAGE=fs-tenant-dev:v16.55.0
FROM ${KIRACI_IMAGE} AS hrms

# The shared tenant image (dev/Dockerfile.tenant) already carries HRMS at this commit. Reuse it then.
RUN if [ ! -d apps/hrms ]; then git clone --depth 1 --branch v16.54.1 https://github.com/frappe/hrms.git apps/hrms; fi \
    && test "$(git -C apps/hrms rev-parse HEAD)" = a01032350ba1b799345b862cb122fa408bf6780e \
    && uv pip install --python env/bin/python --no-deps -e apps/hrms \
    && uv pip check --python env/bin/python \
    && { grep -qxF hrms sites/apps.txt || printf '\nhrms\n' >> sites/apps.txt; }

FROM hrms AS hrms_tr
COPY --chown=frappe:frappe apps/hrms_tr apps/hrms_tr
COPY --chown=frappe:frappe dev/hrms/seed.py dev/hrms/test_http.py dev/hrms/measure.py /workspace/hrms/
COPY --chown=frappe:frappe contracts/hrms_tr.openapi.yaml /workspace/hrms/
RUN uv pip install --python env/bin/python --no-deps -e apps/hrms_tr \
    && uv pip install --python env/bin/python PyYAML==6.0.3 jsonschema==4.26.0 Werkzeug==3.1.9 \
    && { grep -qxF hrms_tr sites/apps.txt || printf '\nhrms_tr\n' >> sites/apps.txt; }
