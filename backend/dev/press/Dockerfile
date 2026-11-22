FROM frappe/bench@sha256:a822a0aedf309582c1d5e49e461a88b5b891b446063b74263c896da92281bd70 AS runtime

USER root
COPY backend/libs/oidc_verify/ /tmp/press-oidc-source/
RUN /home/frappe/.local/bin/uv build --wheel --out-dir /opt/press-local/wheels /tmp/press-oidc-source \
	&& rm -rf /tmp/press-oidc-source
USER frappe

FROM runtime AS runtime-check

FROM runtime AS development

USER root
# `dockerfile==3.2.0` (pinned by press) has no linux-arm64 wheel; its sdist builds with GOPATH-mode
# `go get`, which was removed in Go 1.22. Go 1.21 is installed only for that build.
ARG GO_VERSION=1.21.13
ARG TARGETARCH
RUN arch="${TARGETARCH:-$(dpkg --print-architecture)}" \
	&& case "$arch" in \
		arm64) checksum=2ca2d70dc9c84feef959eb31f2a5aac33eefd8c97fe48f1548886d737bffabd4 ;; \
		amd64) checksum=502fc16d5910562461e6a6631fb6377de2322aad7304bf2bcd23500ba9dab4a7 ;; \
		*) echo "Unsupported Go architecture: $arch" >&2; exit 2 ;; \
	esac \
	&& curl -fsSLo /tmp/go.tgz "https://go.dev/dl/go${GO_VERSION}.linux-$arch.tar.gz" \
	&& echo "${checksum}  /tmp/go.tgz" | sha256sum -c - \
	&& mkdir -p /usr/local/go1.21 \
	&& tar -xzf /tmp/go.tgz -C /usr/local/go1.21 --strip-components=1 \
	&& rm /tmp/go.tgz

COPY backend/dev/press/uv-overrides.txt /opt/press-local/uv-overrides.txt
COPY backend/dev/press/patch-py314.sh /opt/press-local/scripts/patch-py314.sh
COPY backend/dev/press/create_site.py /opt/press-local/scripts/create_site.py
RUN touch /opt/press-local/development-image
ENV GO111MODULE=off \
	PATH=/usr/local/go1.21/bin:$PATH \
	UV_OVERRIDE=/opt/press-local/uv-overrides.txt

USER frappe
