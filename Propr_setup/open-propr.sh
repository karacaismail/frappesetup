#!/bin/sh
# ProPR Desktop'u yalnız kendi Colima profiliyle ("propr") açar.
# Genel Docker bağlamı ("colima") değişmez.
set -eu
colima status propr >/dev/null 2>&1 || colima start propr --activate=false
exec open -a /Applications/propr-desktop.app \
  --env DOCKER_HOST="unix://$HOME/.colima/propr/docker.sock" \
  --env DOCKER_CONFIG="$HOME/.config/propr-docker"
