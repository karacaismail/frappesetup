ARG KIRACI_IMAGE=fs-kiraci-dev:v16.55.0
FROM ${KIRACI_IMAGE} AS hrms

RUN git clone --depth 1 --branch v16.54.1 https://github.com/frappe/hrms.git apps/hrms \
    && test "$(git -C apps/hrms rev-parse HEAD)" = a01032350ba1b799345b862cb122fa408bf6780e \
    && uv pip install --python env/bin/python -e apps/hrms \
    && printf '\nhrms\n' >> sites/apps.txt

FROM hrms AS hrms_tr
COPY --chown=frappe:frappe apps/hrms_tr apps/hrms_tr
COPY --chown=frappe:frappe dev/hrms/seed.py dev/hrms/test_http.py dev/hrms/measure.py /workspace/hrms/
COPY --chown=frappe:frappe contracts/hrms_tr.openapi.yaml /workspace/hrms/
RUN uv pip install --python env/bin/python --no-deps -e apps/hrms_tr \
    && uv pip install --python env/bin/python PyYAML==6.0.3 jsonschema==4.26.0 Werkzeug==3.1.9 \
    && printf '\nhrms_tr\n' >> sites/apps.txt
