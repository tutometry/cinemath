# Shared mautedpc deploy helpers. Sourced by ci-deploy.sh in each repo.

deploy_lib_init() {
  export PATH="${HOME}/.local/bin:/usr/local/bin:${PATH}"

  SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  STACK_DEST="${TUTOMETRY_STACK:-${HOME}/homelab/stacks/tutometry}"
  DATA_DEST="${TUTOMETRY_DATA:-${HOME}/storage/tutometry}"
  API_CODE="${TUTO_API_HOME:-${HOME}/code/tuto-api}"
  WEB_CODE="${TUTO_WEB_HOME:-${HOME}/code/tuto-web}"
  CINEMATH_CODE="${CINEMATH_HOME:-${HOME}/code/cinemath}"
  RUNTIME_IMAGE="${TUTOMETRY_RUNTIME_IMAGE:-oven/bun:1.3}"
  CINEMATH_IMAGE="${CINEMATH_IMAGE:-cinemath-worker:latest}"
  DEFAULT_CINEMATH_WORKER_URL="http://cinemath-worker:8080"
  PORT="${TUTOMETRY_PORT:-8341}"
  ENV_FILE="${TUTOMETRY_ENV_FILE:-${STACK_DEST}/.env}"
}

read_env_keys_file() {
  local file="$1"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line//[[:space:]]/}"
    [[ -z "$line" ]] && continue
    printf '%s\n' "$line"
  done < "$file"
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "ERROR: ${name} is not set. Add it as a GitHub Actions secret and redeploy." >&2
    exit 1
  fi
}

require_env_keys() {
  local file="$1"
  while IFS= read -r key; do
    require_env "$key"
  done < <(read_env_keys_file "$file")
}

deploy_env_value_for_key() {
  local key="$1"
  local value="${!key:-}"
  case "$key" in
    PUBLIC_URL) value="${value:-https://tutometry.mauted.com}" ;;
    CINEMATH_WORKER_URL) value="${value:-${DEFAULT_CINEMATH_WORKER_URL}}" ;;
    SAAS_OPEN_SIGNUP) value="${value:-true}" ;;
    SAAS_SIGNUP_CREDITS) value="${value:-0}" ;;
    STRIPE_CREDIT_PACK_AMOUNT) value="${value:-5}" ;;
  esac
  printf '%s' "$value"
}

ensure_deploy_dirs() {
  mkdir -p "${API_CODE}" "${WEB_CODE}" "${CINEMATH_CODE}" "${STACK_DEST}" \
    "${DATA_DEST}/postgres" "${DATA_DEST}/files" "${DATA_DEST}/cinemath-artifacts}"
}

write_deploy_env_file() {
  local keys_file="${SRC}/deploy/production.env.keys"
  umask 077
  : > "${ENV_FILE}"
  while IFS= read -r key; do
    printf '%s=%s\n' "$key" "$(deploy_env_value_for_key "$key")" >> "${ENV_FILE}"
  done < <(read_env_keys_file "$keys_file")
  cat >> "${ENV_FILE}" <<EOF
SESSION_COOKIE_SECURE=${SESSION_COOKIE_SECURE:-true}
APP_ENV=production
DATA_PATH=${DATA_DEST}/postgres
FILES_PATH=${DATA_DEST}/files
CINEMATH_ARTIFACTS_PATH=${DATA_DEST}/cinemath-artifacts
TUTOMETRY_RUNTIME_IMAGE=${RUNTIME_IMAGE}
TUTO_API_CODE_PATH=${API_CODE}
TUTO_WEB_CODE_PATH=${WEB_CODE}
CINEMATH_IMAGE=${CINEMATH_IMAGE}
CINEMATH_CLASSIFY_PROVIDER=${CINEMATH_CLASSIFY_PROVIDER:-ollama}
OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://host.docker.internal:11434}
OLLAMA_CLASSIFY_MODEL=${OLLAMA_CLASSIFY_MODEL:-llama3.1:8b}
EOF
  echo "    wrote deploy env → ${ENV_FILE}"
}

rsync_repo() {
  local dest="$1"
  rsync -a --delete \
    --exclude '.git/' \
    --exclude 'node_modules/' \
    --exclude 'dist/' \
    --exclude '.venv/' \
    --exclude '.env' \
    --exclude '.env.local' \
    --exclude '**/__pycache__/' \
    --exclude 'outputs/' \
    --exclude 'media/' \
    "${SRC}/" "${dest}/"
}

sync_compose_manifest() {
  cp "${SRC}/deploy/docker-compose.yml" "${STACK_DEST}/docker-compose.yml"
}

setup_compose() {
  COMPOSE=(docker compose -p tutometry --env-file "${ENV_FILE}" -f "${STACK_DEST}/docker-compose.yml")
}

retire_monolith_container() {
  if docker container inspect tutometry >/dev/null 2>&1; then
    echo "    stopping monolith container tutometry"
    docker rm -f tutometry
  fi
}

bun_in() {
  local dest="$1"
  shift
  docker run --rm \
    -v "${dest}:/app" \
    -w /app \
    -e CI=true \
    -e NODE_ENV="${NODE_ENV:-}" \
    "${RUNTIME_IMAGE}" \
    "$@"
}

wait_for_public_health() {
  echo "==> health"
  for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null; then
      echo "    http://127.0.0.1:${PORT}/api/health ok"
      return 0
    fi
    sleep 2
  done
  return 1
}
