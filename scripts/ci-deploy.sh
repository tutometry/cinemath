#!/usr/bin/env bash
# Build and roll out the Cinemath worker image.
set -euo pipefail

# shellcheck source=scripts/deploy-lib.sh
source "$(cd "$(dirname "$0")" && pwd)/deploy-lib.sh"

deploy_lib_init

echo "==> cinemath deploy"
echo "    src: ${SRC}"
echo "    code: ${CINEMATH_CODE}"

ensure_deploy_dirs
require_env_keys "${SRC}/deploy/required-cinemath.keys"
write_deploy_env_file
rsync_repo "${CINEMATH_CODE}"

echo "==> docker build ${CINEMATH_IMAGE}"
docker build -t "${CINEMATH_IMAGE}" "${CINEMATH_CODE}"

sync_compose_manifest
setup_compose

echo "==> compose up (cinemath-worker)"
"${COMPOSE[@]}" up -d --no-deps --force-recreate cinemath-worker
echo "    cinemath-worker rolled out"
