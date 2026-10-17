#!/bin/sh
# Builder needs Docker with buildx and Python 3. Deployment needs only Docker.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
platform=${PLATFORM:-linux/amd64}
case "$platform" in
  linux/amd64) arch=amd64 ;;
  linux/arm64) arch=arm64 ;;
  *) echo 'PLATFORM must be linux/amd64 or linux/arm64' >&2; exit 1 ;;
esac
revision=$(git rev-parse HEAD)
version=${VERSION:-$(git rev-parse --short=12 HEAD)}
case "$version" in
  ''|*[!a-zA-Z0-9_.-]*) echo 'Invalid VERSION' >&2; exit 1 ;;
esac
backend_image="digital-hr-backend:$version-$arch"
frontend_image="digital-hr-frontend:$version-$arch"
postgres_image="digital-hr-postgres:17-$arch"
bundle_dir="$project_dir/dist/digital-hr-$version-$arch"
if [ -e "$bundle_dir" ]; then
  echo "Bundle already exists: $bundle_dir" >&2
  exit 1
fi
docker buildx build --platform "$platform" --load \
  --label "org.opencontainers.image.revision=$revision" \
  --tag "$backend_image" backend
docker buildx build --platform "$platform" --load \
  --label "org.opencontainers.image.revision=$revision" \
  --build-arg API_INTERNAL_URL=http://backend:8000 \
  --tag "$frontend_image" frontend
# A dedicated tag ensures the archive contains the selected PostgreSQL platform.
docker pull --platform "$platform" postgres:17-alpine
docker tag postgres:17-alpine "$postgres_image"
mkdir -p "$bundle_dir/scripts"
docker compose config --no-interpolate --format json > "$bundle_dir/compose.source.json"
python3 - "$bundle_dir" "$platform" "$backend_image" "$frontend_image" "$postgres_image" "$revision" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
platform, backend, frontend, postgres, revision = sys.argv[2:]
config = json.loads((root / 'compose.source.json').read_text())
config.pop('name', None)
for name, service in config['services'].items():
    service.pop('build', None)
    service['image'] = frontend if name == 'frontend' else postgres if name == 'postgres' else backend
    service['platform'] = platform
for kind in ('volumes', 'networks'):
    for resource in config.get(kind, {}).values():
        resource.pop('name', None)
(root / 'compose.json').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
(root / 'compose.source.json').unlink()
(root / 'backend-image.txt').write_text(backend + '\n')
(root / 'revision.txt').write_text(revision + '\n')
PY
cp scripts/deploy.sh "$bundle_dir/deploy.sh"
cp scripts/setup_env.py "$bundle_dir/scripts/setup_env.py"
cp .env.example "$bundle_dir/.env.example"
cp docs/deployment.md "$bundle_dir/README.md"
chmod +x "$bundle_dir/deploy.sh"
docker image save --platform "$platform" --output "$bundle_dir/images.tar" \
  "$backend_image" "$frontend_image" "$postgres_image"
COPYFILE_DISABLE=1 tar -czf "$bundle_dir.tar.gz" -C "$project_dir/dist" "$(basename "$bundle_dir")"
printf 'Bundle: %s.tar.gz\n' "$bundle_dir"
