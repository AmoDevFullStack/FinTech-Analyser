# Deployment

How a change gets from a pull request to production, how to set that up once, and what to
do when a deploy goes wrong.

---

## 1. The pipeline

```
pull request ──▶ ci.yml        lint · format · types · no-float · backend tests (Postgres)
                               migration round-trip · frontend tests + build
                               production image build · Playwright (non-blocking for now)

merge to main ─▶ ci.yml green ─▶ cd.yml: build + push images to GHCR, tagged <commit sha>
                                         └─▶ deploy.yml → staging

tag vX.Y.Z ───▶ cd.yml: re-tag that commit's images as vX.Y.Z (no rebuild)
                        └─▶ deploy.yml → production (waits for a required reviewer)

manual ───────▶ cd.yml "Run workflow": any already-built SHA → staging or production
```

Production only ever runs an image that was built from `main` and passed CI. A release tag
on a commit that never went through the `main` build fails at the promote step on purpose.

Every deploy (`scripts/remote-deploy.sh`, run on the host over SSH):

1. Pulls the images for the commit.
2. Backs up the database with `pg_dump` into `backups/` on the host (the newest ten are kept).
3. Starts Postgres and Redis and waits for them to be healthy.
4. Runs `alembic upgrade head` as a one-off container. If it fails, the deploy stops here and
   the previous release keeps serving untouched.
5. Replaces the backend, worker and web containers and waits for their health checks.
6. Back on the runner, `scripts/smoke_test.py` checks the public URL:
   - `/api/v1/health` is up;
   - `/api/v1/ready` reports the database reachable **and** its schema at this build's
     migration head;
   - `/api/v1/version` reports the commit being deployed (proving the new build is
     answering, not the old one);
   - the frontend serves HTML.
7. If step 5 or 6 fails, the app containers are rolled back to the previous release.

---

## 2. One-time setup

### The host

Any Linux VM with Docker Engine and the Compose plugin. Then:

```bash
sudo mkdir -p /opt/fintech-analyser && sudo chown "$USER" /opt/fintech-analyser
cd /opt/fintech-analyser
cat > .env <<'ENV'
SECRET_KEY=<64 random chars: python3 -c "import secrets; print(secrets.token_urlsafe(48))">
JWT_SECRET_KEY=<a different 64 random chars>
POSTGRES_PASSWORD=<random>
OPENAI_API_KEY=
ENV
chmod 600 .env
```

The deploy copies `docker-compose.prod.yml` and `remote-deploy.sh` in on every run. `.env` is
the only file you create by hand, and it never leaves the host.

Put TLS in front of port 8080 (Caddy, a host Nginx, or a cloud load balancer). Outside
development the app marks session cookies `Secure`, so logins over plain HTTP will not stick.

Create a deploy user with a dedicated SSH key, membership of the `docker` group, and no other
privileges.

### GitHub

1. **Settings → Environments**: create `staging` and `production`. On `production`, add
   *required reviewers* and restrict deployments to tags matching `v*`.
2. In each environment, add:

   | Kind     | Name                 | Value                                                      |
   |----------|----------------------|------------------------------------------------------------|
   | secret   | `DEPLOY_HOST`        | host name or IP                                            |
   | secret   | `DEPLOY_USER`        | the deploy user                                            |
   | secret   | `DEPLOY_SSH_KEY`     | that user's private key                                    |
   | secret   | `DEPLOY_KNOWN_HOSTS` | output of `ssh-keyscan -t ed25519 <host>`, checked by hand |
   | variable | `APP_URL`            | `https://staging.example.com` (no trailing slash)          |
   | variable | `DEPLOY_PATH`        | optional; defaults to `/opt/fintech-analyser`              |

3. **Settings → Secrets and variables → Actions → Variables**: set `DEPLOY_ENABLED` to
   `true`. Until then CD still builds and publishes images on every green `main`, but deploys
   nothing.
4. **Settings → Branches**: protect `main` and require the CI jobs to pass before merging.

---

## 3. Releasing

```bash
git checkout main && git pull
# Wait for CD to finish building this commit (the staging deploy proves it works).
git tag -a v1.2.0 -m "v1.2.0" && git push origin v1.2.0
```

Approve the production deployment when GitHub asks for it.

---

## 4. When a deploy fails

**Automatic.** If the containers fail their health checks or the smoke test fails, the
workflow restores the previous release's containers. If the failure came earlier (pull,
backup or migration), nothing was replaced, so nothing is rolled back.

**Manual.** Run the CD workflow by hand ("Run workflow"), choose the environment, and enter
the SHA of the last good release (the deployment history under *Environments* lists them).
Alternatively, on the host: `bash remote-deploy.sh rollback <failed-sha>`.

**The database is never rolled back automatically.** A container rollback after a migration
leaves the old code running against the new schema. In that case `/api/v1/ready` reports
`schema_current: false` and returns 503; the old code may still work, but the system is
telling you the versions disagree. Choose one of:

- **Roll forward** with a fix. This is usually right when the migration only added things.
- **Restore** the pre-deploy dump:

  ```bash
  docker compose -f docker-compose.prod.yml exec -T postgres \
    pg_restore -U fdt -d fdt --clean --if-exists < backups/pre-<sha>-<time>.dump
  ```

  This loses any writes made since the deploy.

### Keeping migrations rollback-safe

Write migrations so the previous release can run against the new schema
(*expand → migrate → contract*):

- Add columns as nullable or with a default; never rename or drop in the same release that
  stops using a column. Stop using it in one release, drop it in the next.
- Backfill large tables in a worker, not inside the migration.
- Every migration needs a working `downgrade()`. CI's round-trip job enforces that it runs.

### Backups

`backups/` on the host only protects against a bad migration, not against losing the host.
Ship the dumps off-host (object storage with lifecycle rules) before production holds real
financial data.

---

## 5. Deploy checklist

Use for every production release, including routine ones.

### Before tagging
- [ ] CI green on the commit, and the staging deploy of it succeeded
- [ ] Clicked through the changed flows on staging, logged in as the demo user
- [ ] Any new migration follows section 4 (expand/contract) and has a working downgrade
- [ ] New environment variables are added to `.env` on the production host, and to
      `.env.example`
- [ ] Release notes written (what changed, any migration, any new configuration)

### During
- [ ] Approve the production deployment in GitHub
- [ ] The deploy job's summary shows the expected commit
- [ ] Watch the logs for 15 minutes:
      `docker compose -f docker-compose.prod.yml logs -f backend worker`
- [ ] `docker compose -f docker-compose.prod.yml exec backend flask --app wsgi events failed`
      reports no stuck events

### After
- [ ] Key journeys work in production: log in, dashboard loads, run a scenario, import a
      statement
- [ ] Close the related issues and publish the release notes

### Roll back (section 4) if
- [ ] `/api/v1/ready` returns anything but 200 for more than 2 minutes
- [ ] 5xx responses exceed 1% of requests over 5 minutes
- [ ] Login, scenario run, or statement import fails for the demo user
- [ ] `events failed` lists events that did not exist before the deploy
