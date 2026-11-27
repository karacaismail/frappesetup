#!/bin/bash
set -euo pipefail

context="$1"
network="$2"
container="$3"
worktree="$4"
suite_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
docker_preview() { docker --context "$context" "$@"; }

version="$(node -p 'require(process.argv[1]).version' "$worktree/node_modules/playwright/package.json")"
repository=mcr.microsoft.com/playwright
image="$repository:v$version-noble"
if ! docker_preview image inspect "$image" >/dev/null 2>&1; then
    tag="$(docker_preview image ls "$repository" --format '{{.Tag}}' | awk -v prefix="v${version%.*}." '
        index($0, prefix) == 1 && substr($0, length(prefix) + 1) ~ /^[0-9]+-noble$/ { print; exit }
    ')"
    if [[ -z "$tag" ]]; then
        printf 'No local Playwright image for %s in %s.\n' "$version" "$context" >&2
        exit 1
    fi
    image="$repository:$tag"
fi
printf 'Browser runner image: %s\n' "$image"

docker_preview create --pull never --network "$network" --init --shm-size=512m \
    --label "com.frappesetup.preview=$PREVIEW_PROJECT" --name "$container" "$image" sleep infinity >/dev/null
docker_preview start "$container" >/dev/null
docker_preview exec "$container" mkdir -p /suite/backend/e2e /suite/node_modules/.bin /results
docker_preview cp "$suite_dir/." "$container:/suite/backend/e2e/"
for package in @playwright playwright playwright-core; do
    docker_preview cp "$worktree/node_modules/$package" "$container:/suite/node_modules/"
done
docker_preview exec "$container" ln -s ../@playwright/test/cli.js /suite/node_modules/.bin/playwright
docker_preview cp "$PREVIEW_DIR/fixtures.json" "$container:/results/fixtures.json"

settings=(--env PANE_PORT --env AGIR_TEST_YER --env E2E_BROWSER_RUNTIME=container --env PREVIEW_DIR=/results)
while IFS= read -r name; do
    if [[ "$name" =~ ^E2E_[A-Z0-9_]+$ ]]; then
        settings+=(--env "$name")
    fi
done < <(compgen -e)

status=0
docker_preview exec --workdir /suite "${settings[@]}" "$container" \
    node /suite/backend/e2e/preview/container-entry.mjs /suite || status=$?

# Copy only logs that the Node runner has already redacted.
for log in chromium-launch webkit-launch browser api lifecycle chromium-idle webkit-idle chromium-scenarios webkit-scenarios; do
    if docker_preview exec "$container" test -f "/results/$log.log"; then
        docker_preview cp "$container:/results/$log.log" "$PREVIEW_DIR/$log.log"
    fi
done
exit "$status"
