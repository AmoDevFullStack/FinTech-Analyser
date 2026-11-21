#!/usr/bin/env bash
# Runs ON the app host, sent by scripts/aws_deploy.py through SSM Run Command.
#
#   remote-deploy.sh deploy   <image-tag>   render .env, pull, migrate, roll the stack forward
#   remote-deploy.sh rollback <image-tag>   undo a deploy of <image-tag>, if it got as far
#                                           as replacing containers
#
# Works in the deploy directory, where aws_deploy.py has just put docker-compose.prod.yml,
# this script and the Caddyfile. Writes .deployed-tag and .previous-tag there, so a rollback
# knows where to go without asking the pipeline.
#
# Environment (exported by aws_deploy.py):
#   IMAGE_REGISTRY       <account>.dkr.ecr.<region>.amazonaws.com/fintech-analyser
#   SSM_PARAMETER_PATH   /fintech-analyser/<env>/app — rendered into .env on every deploy
#   AWS_REGION
#
# The database is backed up by aws_deploy.py (an RDS snapshot) before this script runs.
set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
APP_SERVICES=(backend worker web caddy)

log() { printf '[deploy %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die() { log "$*"; exit 1; }

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

# A half-written .env temp file may hold secrets; remove it however the script exits.
ENV_TMP=""
cleanup() { if [[ -n "$ENV_TMP" ]]; then rm -f "$ENV_TMP"; fi; }
trap cleanup EXIT

render_env() {
    # Configuration lives in Parameter Store, not on the host: each deploy rewrites .env from
    # it, so a changed secret takes effect on the next deploy and the host holds no state
    # worth backing up. Without SSM_PARAMETER_PATH, a hand-written .env is used as-is.
    if [[ -z "${SSM_PARAMETER_PATH:-}" ]]; then
        [[ -f .env ]] || die "no SSM_PARAMETER_PATH and no .env in $(pwd)"
        return
    fi
    ENV_TMP="$(mktemp .env.XXXXXX)"
    chmod 600 "$ENV_TMP"
    aws ssm get-parameters-by-path \
        --path "$SSM_PARAMETER_PATH" \
        --with-decryption \
        --query 'Parameters[].[Name,Value]' \
        --output text \
        | while IFS=$'\t' read -r name value; do
            printf '%s=%s\n' "${name##*/}" "$value"
        done > "$ENV_TMP"
    grep -q '^DATABASE_URL=' "$ENV_TMP" \
        || die "no DATABASE_URL under $SSM_PARAMETER_PATH — has Terraform been applied?"
    mv "$ENV_TMP" .env
    ENV_TMP=""
    log "rendered .env from $SSM_PARAMETER_PATH ($(wc -l < .env) settings)"
}

registry_login() {
    local registry="${IMAGE_REGISTRY:?IMAGE_REGISTRY is not set}"
    registry="${registry%%/*}"
    if [[ "$registry" == *.dkr.ecr.*.amazonaws.com ]]; then
        # Credentials come from the instance role; the token is valid for 12 hours.
        aws ecr get-login-password | docker login --username AWS --password-stdin "$registry" >/dev/null
    fi
}

deploy() {
    IMAGE_TAG="${1:?usage: remote-deploy.sh deploy <image-tag>}"
    export IMAGE_TAG

    render_env
    registry_login

    log "pulling images for $IMAGE_TAG"
    compose pull --quiet

    log "starting redis"
    compose up -d --wait redis

    log "running migrations"
    compose run --rm migrate

    # Bookkeeping BEFORE replacing containers: from here on the old ones may be gone, so a
    # rollback has to know what they were even if `up` fails halfway.
    if [[ -f .deployed-tag ]] && [[ "$(cat .deployed-tag)" != "$IMAGE_TAG" ]]; then
        cp .deployed-tag .previous-tag
    fi
    printf '%s\n' "$IMAGE_TAG" > .deployed-tag

    log "rolling application containers"
    compose up -d --wait --remove-orphans "${APP_SERVICES[@]}"

    docker image prune -af --filter "until=168h" >/dev/null || true
    log "deployed $IMAGE_TAG"
}

rollback() {
    local attempted="${1:?usage: remote-deploy.sh rollback <attempted-image-tag>}"
    if [[ "$(cat .deployed-tag 2>/dev/null)" != "$attempted" ]]; then
        # The failed deploy stopped before touching containers (render, pull or migration
        # failed), so what is running is still the last good release. Leave it alone.
        log "$attempted never replaced the running containers — nothing to roll back"
        return
    fi
    [[ -f .previous-tag ]] || die "no previous tag recorded — nothing to roll back to"

    IMAGE_TAG="$(cat .previous-tag)"
    export IMAGE_TAG
    render_env
    registry_login
    log "rolling back application containers to $IMAGE_TAG (database is NOT rolled back)"
    compose up -d --wait --remove-orphans "${APP_SERVICES[@]}"
    printf '%s\n' "$IMAGE_TAG" > .deployed-tag
    log "rolled back to $IMAGE_TAG"
}

case "${1:-}" in
    deploy) shift; deploy "$@" ;;
    rollback) shift; rollback "$@" ;;
    *) echo "usage: $0 {deploy|rollback} <image-tag>" >&2; exit 2 ;;
esac
