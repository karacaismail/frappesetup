#!/bin/bash
set -euo pipefail
umask 077

context="$1"
sync="$2"
tenant="$3"
upstream_port="$4"
keycloak_port="$5"
private="$6"
suite="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
docker_preview() { docker --context "$context" "$@"; }
mkdir "$private"
cat > "$private/openssl.conf" <<'CONFIG'
[req]
distinguished_name=preview
x509_extensions=tls
prompt=no
[preview]
CN=identity-sync
[tls]
subjectAltName=DNS:identity-sync
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
CONFIG
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -config "$private/openssl.conf" \
    -keyout "$private/key.pem" -out "$private/certificate.pem" > /dev/null 2>&1
# The merge preview image has env/bin/python. The local stack image has python on PATH.
sync_python="$(docker_preview exec "$sync" sh -c 'if [ -x env/bin/python ]; then echo env/bin/python; else command -v python; fi')"
relay_dir="$(docker_preview exec "$sync" "$sync_python" -c 'import tempfile; print(tempfile.mkdtemp(prefix="e2e-session-tls-"))')"
docker_preview cp "$suite/session_tls.py" "$sync:$relay_dir/relay.py"
docker_preview cp "$private/certificate.pem" "$sync:$relay_dir/certificate.pem"
docker_preview cp "$private/key.pem" "$sync:$relay_dir/key.pem"
uid="$(docker_preview exec "$sync" id -u)"
gid="$(docker_preview exec "$sync" id -g)"
docker_preview exec --user root "$sync" chown -R "$uid:$gid" "$relay_dir"
docker_preview cp "$private/certificate.pem" "$tenant:/usr/local/share/ca-certificates/e2e-identity-sync.crt"
docker_preview exec --user root "$tenant" chmod 0644 /usr/local/share/ca-certificates/e2e-identity-sync.crt
docker_preview exec --user root "$tenant" update-ca-certificates > /dev/null
# update-ca-certificates lasts only as long as this container. Compose recreates the tenant from
# the image, so the certificate is also kept in the sites volume. The tenant entrypoint in
# dev/compose.tenant.yaml adds it to the CA bundle at every start (AJA-936).
docker_preview exec -i --user root "$tenant" sh -c \
    'mkdir -p sites/.e2e-trust && cat > sites/.e2e-trust/identity-sync.crt && chmod 0644 sites/.e2e-trust/identity-sync.crt' \
    < "$private/certificate.pem"
docker_preview exec -d "$sync" "$sync_python" "$relay_dir/relay.py" sessions "$upstream_port"
docker_preview exec -d "$sync" "$sync_python" "$relay_dir/relay.py" keycloak "$keycloak_port"
