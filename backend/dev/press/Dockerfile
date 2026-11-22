FROM frappe/bench:latest

USER root
# `dockerfile==3.2.0` (pinned by press) has no linux-arm64 wheel; its sdist builds with GOPATH-mode
# `go get`, which was removed in Go 1.22. Go 1.21 is installed only for that build.
ARG GO_VERSION=1.21.13
ARG GO_SHA256=2ca2d70dc9c84feef959eb31f2a5aac33eefd8c97fe48f1548886d737bffabd4
RUN curl -fsSLo /tmp/go.tgz "https://go.dev/dl/go${GO_VERSION}.linux-arm64.tar.gz" \
	&& echo "${GO_SHA256}  /tmp/go.tgz" | sha256sum -c - \
	&& mkdir -p /usr/local/go1.21 \
	&& tar -xzf /tmp/go.tgz -C /usr/local/go1.21 --strip-components=1 \
	&& rm /tmp/go.tgz

COPY uv-overrides.txt /opt/press-local/uv-overrides.txt
ENV GO111MODULE=off \
	PATH=/usr/local/go1.21/bin:$PATH \
	UV_OVERRIDE=/opt/press-local/uv-overrides.txt

USER frappe
