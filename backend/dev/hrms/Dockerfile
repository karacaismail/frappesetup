ARG TENANT_IMAGE=fs-tenant-dev:v16.55.0
FROM ${TENANT_IMAGE} AS hrms

RUN git clone --depth 1 --branch v16.54.1 https://github.com/frappe/hrms.git apps/hrms \
    && test "$(git -C apps/hrms rev-parse HEAD)" = a01032350ba1b799345b862cb122fa408bf6780e \
    && uv pip install --python env/bin/python -e apps/hrms \
    && printf '\nhrms\n' >> sites/apps.txt

FROM hrms AS cronhr
COPY --chown=frappe:frappe apps/cronhr apps/cronhr
COPY --chown=frappe:frappe dev/hrms/seed.py dev/hrms/test_http.py /workspace/hrms/
RUN uv pip install --python env/bin/python --no-deps -e apps/cronhr \
    && printf '\ncronhr\n' >> sites/apps.txt
