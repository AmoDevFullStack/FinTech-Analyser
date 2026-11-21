# Deployment

How a change gets from a pull request to production on AWS, how to set AWS up from an empty
account, and what to do when a deploy goes wrong.

---

## 1. What runs where

```
                 ┌──────────────────────── VPC (one per environment) ───────────────────────┐
                 │  public subnet                          private subnets (no internet)    │
 browser ──443──▶│  EC2 (Amazon Linux 2023, Docker)                                         │
                 │   caddy  ── TLS, Let's Encrypt                                           │
                 │   web    ── Nginx: built SPA + /api proxy                                │
                 │   backend (gunicorn) ─────────────────────5432──▶  RDS PostgreSQL 16    │
                 │   worker  (rq)                                      encrypted, backups,  │
                 │   redis   (queue + rate limits)                     point-in-time restore│
                 └──────────────────────────────────────────────────────────────────────────┘
 Shared: ECR (images) · SSM Parameter Store (config, secrets) · S3 (release files, TF state)
```

- **No SSH.** Port 22 is closed; shell access and deploys both go through SSM.
- **No AWS keys in GitHub.** Workflows assume IAM roles through GitHub's OIDC tokens. The
  production deploy role can only be assumed by a job in the `production` GitHub environment,
  so its approval rule also gates its AWS credentials.
- **The database is the only stateful part.** The EC2 host can be replaced at any time: its
  configuration is rendered from Parameter Store on every deploy, and its images come from ECR.

Everything is Terraform, in `infrastructure/terraform/`:

| Stack                  | Holds                                                         | Applied     |
|------------------------|---------------------------------------------------------------|-------------|
| `bootstrap/`           | S3 bucket for Terraform state                                 | once        |
| `global/`              | ECR repositories, GitHub OIDC provider, image build role, cost budget | once |
| `envs/staging/`        | VPC, EC2, RDS, parameters, release bucket, deploy role        | per change  |
| `envs/production/`     | the same, sized and protected for real data                   | per change  |

### Rough monthly cost

On-demand prices in af-south-1 (Cape Town), which runs somewhat above us-east-1. These are
estimates for planning, not quotes: check the AWS Pricing Calculator before committing.

| Item                          | Staging                  | Production                    |
|-------------------------------|--------------------------|-------------------------------|
| EC2 t3.small + 30 GB gp3      | ~$20–25                  | ~$20–25                       |
| RDS PostgreSQL                | db.t3.micro, ~$15–20     | db.t3.small, ~$30–40          |
| Elastic IP, S3, ECR, SSM      | ~$5                      | ~$5                           |
| **Total**                     | **roughly $40–50**       | **roughly $55–70**            |

Multi-AZ RDS (`db_multi_az = true`) roughly doubles the database line. The `global` stack
creates a budget that emails you at 80% of `monthly_budget_usd` actual spend and at 100%
forecast.

---

## 2. The pipeline

```
pull request ──▶ ci.yml   lint · format · types · no-float · backend tests (Postgres) ·
                          migration round-trip · frontend tests + build · image build ·
                          deploy tooling tests (moto) · terraform validate · Playwright

merge to main ─▶ ci.yml green ─▶ cd.yml: build + push to ECR, tagged <commit sha>
                                         └─▶ deploy.yml → staging

tag vX.Y.Z ───▶ cd.yml: re-tag that commit's images as vX.Y.Z (no rebuild)
                        └─▶ deploy.yml → production (waits for a required reviewer)

manual ───────▶ cd.yml "Run workflow": any already-built SHA → either environment (rollback)
```

Every deploy (`scripts/aws_deploy.py`, then `scripts/remote-deploy.sh` on the host):

1. Uploads `docker-compose.prod.yml`, `remote-deploy.sh` and the `Caddyfile` for the commit
   to the environment's S3 release bucket.
2. Takes an RDS snapshot named `predeploy-<env>-<sha>-<time>` and waits for it. The newest
   ten are kept.
3. On the host, through SSM Run Command:
   1. Renders `.env` from `/fintech-analyser/<env>/app/*` in Parameter Store.
   2. Logs in to ECR and pulls the images.
   3. Runs `alembic upgrade head`. If it fails, the deploy stops here and the previous
      release keeps serving untouched.
   4. Replaces the backend, worker, web and Caddy containers and waits for their health
      checks.
4. Back on the runner, `scripts/smoke_test.py` checks the public URL:
   - `/api/v1/health` is up;
   - `/api/v1/ready` reports the database reachable **and** at this build's migration head;
   - `/api/v1/version` reports the commit being deployed;
   - the frontend serves HTML.
5. If step 3.4 or 4 fails, the containers are rolled back to the previous release.

---

## 3. Setting up AWS from an empty account

Allow an afternoon. Do staging first, end to end, before production.

### 3.1 The account

1. Create the AWS account. On the root user, turn on MFA, then stop using root for anything
   else.
2. Enable **IAM Identity Center** and create yourself a user with the
   `AdministratorAccess` permission set. Sign in with that user from now on.
3. **Account → AWS Regions**: enable **Africa (Cape Town) af-south-1**. It is opt-in and takes
   a few minutes to activate. It keeps users' financial data in South Africa, which keeps
   POPIA's cross-border transfer rules out of the picture. To use another region, change
   `aws_region` in each stack.
4. On your machine, install the **AWS CLI v2**, the **Session Manager plugin** for the CLI,
   and **Terraform ≥ 1.10**. Then run `aws configure sso`, give the profile a name, and
   `export AWS_PROFILE=<that name>`.

### 3.2 Terraform state

```bash
cd infrastructure/terraform/bootstrap
terraform init && terraform apply
terraform output -raw backend_hcl > ../backend.hcl
```

### 3.3 Shared resources

```bash
cd ../global
cp terraform.tfvars.example terraform.tfvars   # set budget_alert_email
terraform init -backend-config=../backend.hcl
terraform apply
terraform output     # note github_build_role_arn
```

If you renamed the GitHub repository or its owner, set `github_repository` exactly as GitHub
shows it. IAM compares it case-sensitively, and a mismatch shows up as "Not authorized to
perform sts:AssumeRoleWithWebIdentity".

### 3.4 Staging

```bash
cd ../envs/staging
cp terraform.tfvars.example terraform.tfvars   # set app_domain, e.g. staging.example.com
terraform init -backend-config=../../backend.hcl
terraform apply      # ~10 minutes, mostly RDS
terraform output     # public_ip, deploy_role_arn, app_url
```

**DNS.** Create an `A` record for `app_domain` pointing at `public_ip`. If the domain is in
Route 53, set `route53_zone_id` in `terraform.tfvars` and Terraform creates the record. Caddy
requests the TLS certificate on first start, so the record must resolve before the first
deploy. Otherwise Caddy keeps retrying with backoff and HTTPS stays down until it succeeds.

**Optional settings.** Anything under `/fintech-analyser/staging/app/` becomes an environment
variable on the next deploy:

```bash
aws ssm put-parameter --type SecureString \
  --name /fintech-analyser/staging/app/OPENAI_API_KEY --value 'sk-...'
```

### 3.5 GitHub

1. **Settings → Secrets and variables → Actions → Variables** (repository):
   - `AWS_REGION` = `af-south-1`
   - `AWS_BUILD_ROLE_ARN` = `github_build_role_arn` from 3.3

   Until both are set, CD does nothing; CI runs regardless.
2. **Settings → Environments → New environment `staging`**, with these variables:
   - `AWS_DEPLOY_ROLE_ARN` = `deploy_role_arn` from 3.4
   - `APP_URL` = `app_url` from 3.4, e.g. `https://staging.example.com`
3. **Settings → Branches**: protect `main` and require the CI jobs to pass before merging.

### 3.6 First deploy

Merge anything to `main`, or re-run the latest CI run on `main`. CD builds the images,
pushes them to ECR, and deploys to staging. Then seed a demo user to click through:

```bash
aws ssm start-session --target "$(terraform output -raw instance_id)"
# then, on the host:
sudo -i
cd /opt/fintech-analyser
docker compose -f docker-compose.prod.yml exec backend flask --app wsgi seed demo
```

### 3.7 Production

Repeat 3.4 in `envs/production` with the production domain. Then repeat 3.5 step 2 for an
environment named `production`, plus:

- **Required reviewers**: at least yourself.
- **Deployment branches and tags**: only tags matching `v*`.

---

## 4. Releasing

```bash
git checkout main && git pull
# Wait for CD to finish this commit's staging deploy: that proves the image works.
git tag -a v1.2.0 -m "v1.2.0" && git push origin v1.2.0
```

Approve the production deployment when GitHub asks for it.

---

## 5. Operating it

| Task | How |
|---|---|
| Shell on the host | `aws ssm start-session --target <instance_id>`, then `sudo -i; cd /opt/fintech-analyser` |
| Logs | `docker compose -f docker-compose.prod.yml logs -f backend worker` |
| Stuck domain events | `docker compose -f docker-compose.prod.yml exec backend flask --app wsgi events failed` |
| Change a setting or secret | `aws ssm put-parameter --overwrite ...`, then redeploy (CD → Run workflow, same SHA) |
| Rotate the database password | `terraform apply -replace=module.environment.random_password.db`, then redeploy at once: the app fails to connect in between |
| Replace the host | `terraform apply -replace=module.environment.aws_instance.app`, update DNS if the IP changed, then redeploy |
| What is deployed | `curl https://<domain>/api/v1/version` |

Security patches install automatically on the host (`dnf-automatic`, security updates only).
Kernel updates take effect after a reboot (`sudo reboot`); containers restart on their own.

---

## 6. When a deploy fails

**Automatic.** If the containers fail their health checks or the smoke test fails, the
workflow restores the previous release's containers. If the failure came earlier (rendering
the configuration, pulling, the snapshot, or the migration), nothing was replaced, so nothing
is rolled back.

**Manual.** Run the CD workflow by hand ("Run workflow"), choose the environment, and enter
the SHA of the last good release (the deployment history under *Environments* lists them).

**The database is never rolled back automatically.** A container rollback after a migration
leaves the old code running against the new schema. In that case `/api/v1/ready` reports
`schema_current: false` and returns 503; the old code may still work, but the versions
disagree. Choose one of:

- **Roll forward** with a fix. This is usually right when the migration only added things.
- **Restore** from the snapshot the deploy took. RDS always restores into a *new* instance:

  ```bash
  aws rds restore-db-instance-from-db-snapshot \
    --db-instance-identifier fintech-analyser-<env>-restored \
    --db-snapshot-identifier predeploy-<env>-<sha>-<time> \
    --db-subnet-group-name fintech-analyser-<env> \
    --vpc-security-group-ids <db security group id> --no-publicly-accessible
  ```

  Then point `/fintech-analyser/<env>/app/DATABASE_URL` at the new endpoint and redeploy the
  previous release. Writes made since the snapshot are lost. The restored instance is not in
  Terraform's state, so reconcile afterwards (import it, or restore back into place during a
  maintenance window). Practise this on staging before you need it on production.
- **Point-in-time restore** (`restore-db-instance-to-point-in-time`) works the same way, to
  any second within the backup retention window.

### Keeping migrations rollback-safe

Write migrations so that the previous release can still run against the new schema
(*expand → migrate → contract*):

- Add columns as nullable or with a default. Never rename or drop a column in the same
  release that stops using it: stop using it in one release, drop it in the next.
- Backfill large tables in a worker, not inside the migration.
- Every migration needs a working `downgrade()`. CI's round-trip job enforces that it runs.

---

## 7. Deploy checklist

Use for every production release, including routine ones.

### Before tagging
- [ ] CI is green on the commit, and the staging deploy of it succeeded
- [ ] Clicked through the changed flows on staging
- [ ] Any new migration follows section 6 (expand/contract) and has a working downgrade
- [ ] New settings exist in Parameter Store for production
      (`/fintech-analyser/production/app/...`) and in `.env.example`
- [ ] Release notes written (what changed, any migration, any new setting)

### During
- [ ] Approve the production deployment in GitHub
- [ ] The deploy job's summary shows the expected commit
- [ ] Watch `logs -f backend worker` (section 5) for 15 minutes
- [ ] `events failed` reports no stuck events

### After
- [ ] Key journeys work in production: log in, dashboard loads, run a scenario, import a
      statement
- [ ] Close the related issues and publish the release notes

### Roll back (section 6) if
- [ ] `/api/v1/ready` returns anything but 200 for more than 2 minutes
- [ ] 5xx responses exceed 1% of requests over 5 minutes
- [ ] Login, scenario run, or statement import fails
- [ ] `events failed` lists events that did not exist before the deploy
