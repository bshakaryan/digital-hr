#!/bin/sh
# Run from a bundle produced by build-deploy.sh. Requires only Docker Compose.
set -eu
bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$bundle_dir"
if [ ! -f compose.json ] || [ ! -f images.tar ]; then
  echo 'Запустите deploy.sh из распакованного Docker-комплекта.' >&2
  exit 1
fi
docker compose version >/dev/null
docker load --input images.tar
backend_image=$(cat backend-image.txt)
if [ ! -f .env ]; then
  docker run --rm --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$bundle_dir,target=/workspace" \
    --workdir /workspace --entrypoint python "$backend_image" scripts/setup_env.py
fi
docker compose --project-name "${DEPLOY_PROJECT:-digital-hr}" --file compose.json \
  up --detach --no-build --pull never --wait --wait-timeout 240
