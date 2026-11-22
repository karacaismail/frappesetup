ARG KIRACI_IMAGE=fs-kiraci-dev:v16.55.0
FROM ${KIRACI_IMAGE} AS hrms

RUN git clone --depth 1 --branch v16.54.1 https://github.com/frappe/hrms.git apps/hrms \
    && test "$(git -C apps/hrms rev-parse HEAD)" = a01032350ba1b799345b862cb122fa408bf6780e \
    && uv pip install --python env/bin/python -e apps/hrms \
    && printf '\nhrms\n' >> sites/apps.txt
