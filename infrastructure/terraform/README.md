# Terraform (AWS)

Order of first use, and everything else, is in [docs/deployment.md](../../docs/deployment.md) §3.

```
bootstrap/              state bucket (local state; apply once)
global/                 ECR, GitHub OIDC provider + build role, budget (apply once)
modules/environment/    VPC, EC2 app host, RDS, SSM parameters, release bucket, deploy role
envs/staging/           module call, sized small and disposable
envs/production/        module call, deletion-protected, 14 days of point-in-time restore
```

After the first `terraform init` in each stack, commit its `.terraform.lock.hcl` so every
machine and CI resolve the same provider versions.
