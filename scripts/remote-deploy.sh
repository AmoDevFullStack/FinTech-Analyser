#!/usr/bin/env bash
# Runs ON the deploy host, invoked over SSH by .github/workflows/deploy.yml.
#
#   remote-deploy.sh deploy   <image-tag>   back up, migrate, roll the stack forward
#   remote-deploy.sh rollback <image-tag>   undo a deploy of <image-tag>, if it got as far
#                                           as replacing containers
#
# Expects, in the working directory (DEPLOY_PATH): docker-compose.prod.yml (copied in by the
# workflow) and .env (created once by hand — see docs/deployment.md). Writes .deployed-tag
# and .previous-tag so a rollback knows where to go without asking the pipeline.
#
# Environment from the workflow: IMAGE_REGISTRY, and REGISTRY_USER/REGISTRY_TOKEN to pull.
set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
BACKUP_DIR="backups"
BACKUPS_KEPT=10

log() { printf '[deploy %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

registry_login() {
    if [[ -n "${REGISTRY_TOKEN:-}" ]]; then
        printf '%s' "$REGISTRY_TOKEN" | docker login ghcr.io -u "${REGISTRY_USER:?}" --password-stdin >/dev/null
    fi
}

backup_database() {
    # Before every migration, because a migration is the one step a container rollback
    # cannot undo. Skipped on a first deploy, when there is no database yet to lose.
    if ! compose ps --status running --services | grep -qx postgres; then
        log "postgres not running yet (first deploy?) — skipping backup"
        return
    fi
    mkdir -p "$BACKUP_DIR"
    local file
    file="$BACKUP_DIR/pre-${IMAGE_TAG:0:12}-$(date -u +%Y%m%dT%H%M%SZ).dump"
    log "backing up database to $file"
    # shellcheck disable=SC2016  # $POSTGRES_* expand inside the container, not here.
    compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > "$file"
    # Keep the newest few; financial data backups also belong off-host (docs/deployment.md).
    find "$BACKUP_DIR" -maxdepth 1 -name 'pre-*.dump' -printf '%T@ %p\n' \
        | sort -rn | tail -n +$((BACKUPS_KEPT + 1)) | cut -d' ' -f2- | xargs -r rm --
}

deploy() {
    IMAGE_TAG="${1:?usage: remote-deploy.sh deploy <image-tag>}"
    export IMAGE_TAG

    [[ -f .env ]] || { log "missing .env in $(pwd) — see docs/deployment.md"; exit 1; }

    registry_login
    log "pulling images for $IMAGE_TAG"
    compose pull --quiet

    backup_database

    log "starting data services"
    compose up -d --wait postgres redis

    log "running migrations"
    compose run --rm migrate

    # Bookkeeping BEFORE replacing containers: from here on the old ones may be gone, so a
    # rollback has to know what they were even if `up` fails halfway.
    if [[ -f .deployed-tag ]] && [[ "$(cat .deployed-tag)" != "$IMAGE_TAG" ]]; then
        cp .deployed-tag .previous-tag
    fi
    printf '%s\n' "$IMAGE_TAG" > .deployed-tag

    log "rolling application containers"
    compose up -d --wait --remove-orphans backend worker web

    docker image prune -f --filter "until=168h" >/dev/null || true
    log "deployed $IMAGE_TAG"
}

rollback() {
    local attempted="${1:?usage: remote-deploy.sh rollback <attempted-image-tag>}"
    if [[ "$(cat .deployed-tag 2>/dev/null)" != "$attempted" ]]; then
        # The failed deploy stopped before touching containers (pull, backup or migration
        # failed), so what is running is still the last good release. Leave it alone.
        log "$attempted never replaced the running containers — nothing to roll back"
        return
    fi
    if [[ ! -f .previous-tag ]]; then
        log "no previous tag recorded — nothing to roll back to"
        exit 1
    fi
    IMAGE_TAG="$(cat .previous-tag)"
    export IMAGE_TAG
    registry_login
    log "rolling back application containers to $IMAGE_TAG (database is NOT rolled back)"
    compose up -d --wait --remove-orphans backend worker web
    printf '%s\n' "$IMAGE_TAG" > .deployed-tag
    log "rolled back to $IMAGE_TAG"
}

case "${1:-}" in
    deploy) shift; deploy "$@" ;;
    rollback) shift; rollback "$@" ;;
    *) echo "usage: $0 {deploy|rollback} <image-tag>" >&2; exit 2 ;;
esac
