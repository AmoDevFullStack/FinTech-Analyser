#!/usr/bin/env python3
"""Deploy a built commit to an AWS environment, or roll a failed deploy back.

    python scripts/aws_deploy.py deploy   --environment staging --image-tag <sha>
    python scripts/aws_deploy.py rollback --environment staging --image-tag <sha>

Called by .github/workflows/deploy.yml with credentials from the environment's OIDC deploy
role. Everything else it needs is in one SSM parameter Terraform writes,
/<project>/<environment>/deploy/config, so the workflow carries no infrastructure IDs.

A deploy:

1. Uploads the release files for the commit to the environment's S3 release bucket.
2. Snapshots the RDS database (`predeploy-<env>-<sha>-<time>`), waits for the snapshot,
   and prunes old pre-deploy snapshots. The migration in step 3 is the one change a
   container rollback cannot undo, so this snapshot is taken before every deploy.
3. Runs scripts/remote-deploy.sh on the app host through SSM Run Command (no SSH): render
   .env from Parameter Store, pull images from ECR, migrate, roll the containers.
4. Streams the host's output into the job log and exits non-zero if the host failed.

Rollback runs `remote-deploy.sh rollback <sha>` on the host, which is a no-op if the failed
deploy never got as far as replacing containers.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from mypy_boto3_rds import RDSClient
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_ssm import SSMClient

PROJECT = "fintech-analyser"
REPO_ROOT = Path(__file__).resolve().parent.parent

# Repository path -> file name on the host. All land flat in the deploy directory, where
# docker-compose.prod.yml expects ./Caddyfile beside it.
RELEASE_FILES: dict[str, str] = {
    "docker-compose.prod.yml": "docker-compose.prod.yml",
    "scripts/remote-deploy.sh": "remote-deploy.sh",
    "infrastructure/caddy/Caddyfile": "Caddyfile",
}

# Full or abbreviated commit SHA. Validated because it is interpolated into a shell command
# on the host and into S3 keys and snapshot names.
IMAGE_TAG_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
ENVIRONMENT_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,20}$")

TERMINAL_STATUSES = frozenset({"Success", "Cancelled", "TimedOut", "Failed"})


class DeployError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class DeployConfig:
    region: str
    instance_id: str
    db_instance_id: str
    release_bucket: str
    image_registry: str
    app_parameter_path: str
    deploy_path: str
    predeploy_snapshots_kept: int

    @classmethod
    def parameter_name(cls, environment: str) -> str:
        return f"/{PROJECT}/{environment}/deploy/config"

    @classmethod
    def load(cls, ssm: SSMClient, environment: str) -> DeployConfig:
        name = cls.parameter_name(environment)
        try:
            raw = ssm.get_parameter(Name=name)["Parameter"]["Value"]
        except ClientError as error:
            raise DeployError(
                f"cannot read {name}: {error}. Has Terraform been applied for {environment}?"
            ) from error
        data: dict[str, Any] = json.loads(raw)
        return cls(
            region=str(data["region"]),
            instance_id=str(data["instance_id"]),
            db_instance_id=str(data["db_instance_id"]),
            release_bucket=str(data["release_bucket"]),
            image_registry=str(data["image_registry"]),
            app_parameter_path=str(data["app_parameter_path"]),
            deploy_path=str(data["deploy_path"]),
            predeploy_snapshots_kept=int(data.get("predeploy_snapshots_kept", 10)),
        )


@dataclass(frozen=True, slots=True)
class CommandResult:
    command_id: str
    status: str
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.status == "Success"


def validate_inputs(environment: str, image_tag: str) -> None:
    if not ENVIRONMENT_PATTERN.fullmatch(environment):
        raise DeployError(f"invalid environment name: {environment!r}")
    if not IMAGE_TAG_PATTERN.fullmatch(image_tag):
        raise DeployError(f"image tag must be a lowercase hex commit SHA, got {image_tag!r}")


def release_prefix(image_tag: str) -> str:
    return f"releases/{image_tag}/"


def upload_release(
    s3: S3Client, config: DeployConfig, image_tag: str, repo_root: Path = REPO_ROOT
) -> list[str]:
    """Upload the release files for `image_tag`; return the S3 keys written."""
    keys: list[str] = []
    for source, target in RELEASE_FILES.items():
        path = repo_root / source
        if not path.is_file():
            raise DeployError(f"release file missing from checkout: {source}")
        key = f"{release_prefix(image_tag)}{target}"
        s3.put_object(Bucket=config.release_bucket, Key=key, Body=path.read_bytes())
        keys.append(key)
    print(
        f"uploaded {len(keys)} release files to s3://{config.release_bucket}/{release_prefix(image_tag)}"
    )
    return keys


def snapshot_name(environment: str, image_tag: str, now: datetime) -> str:
    # RDS: letters, digits and single hyphens, starting with a letter.
    return f"predeploy-{environment}-{image_tag[:12]}-{now.strftime('%Y%m%d%H%M%S')}"


def snapshot_database(
    rds: RDSClient,
    config: DeployConfig,
    environment: str,
    image_tag: str,
    *,
    now: datetime | None = None,
    wait_delay: int = 15,
    wait_attempts: int = 120,
) -> str:
    """Take a manual snapshot before migrating; wait until it is usable; prune old ones."""
    identifier = snapshot_name(environment, image_tag, now or datetime.now(UTC))

    # A snapshot cannot start while the instance is mid-backup or mid-maintenance.
    rds.get_waiter("db_instance_available").wait(
        DBInstanceIdentifier=config.db_instance_id,
        WaiterConfig={"Delay": wait_delay, "MaxAttempts": wait_attempts},
    )
    print(f"creating snapshot {identifier}")
    rds.create_db_snapshot(
        DBSnapshotIdentifier=identifier,
        DBInstanceIdentifier=config.db_instance_id,
        Tags=[
            {"Key": "Purpose", "Value": "predeploy"},
            {"Key": "ImageTag", "Value": image_tag},
            {"Key": "Environment", "Value": environment},
        ],
    )
    rds.get_waiter("db_snapshot_available").wait(
        DBSnapshotIdentifier=identifier,
        WaiterConfig={"Delay": wait_delay, "MaxAttempts": wait_attempts},
    )
    print(f"snapshot {identifier} available")
    prune_snapshots(rds, config, environment)
    return identifier


def prune_snapshots(rds: RDSClient, config: DeployConfig, environment: str) -> list[str]:
    """Delete pre-deploy snapshots beyond the newest `predeploy_snapshots_kept`."""
    prefix = f"predeploy-{environment}-"
    snapshots: list[tuple[datetime, str]] = []
    paginator = rds.get_paginator("describe_db_snapshots")
    for page in paginator.paginate(
        DBInstanceIdentifier=config.db_instance_id, SnapshotType="manual"
    ):
        for snapshot in page["DBSnapshots"]:
            identifier = snapshot["DBSnapshotIdentifier"]
            created = snapshot.get("SnapshotCreateTime")
            if identifier.startswith(prefix) and snapshot.get("Status") == "available" and created:
                snapshots.append((created, identifier))

    snapshots.sort(reverse=True)
    expired = [identifier for _, identifier in snapshots[config.predeploy_snapshots_kept :]]
    for identifier in expired:
        rds.delete_db_snapshot(DBSnapshotIdentifier=identifier)
        print(f"deleted old snapshot {identifier}")
    return expired


def host_commands(config: DeployConfig, action: str, image_tag: str) -> list[str]:
    """The shell lines SSM runs on the host, every interpolated value quoted."""
    path = shlex.quote(config.deploy_path)
    source = shlex.quote(f"s3://{config.release_bucket}/{release_prefix(image_tag)}")
    exports = " ".join(
        f"{name}={shlex.quote(value)}"
        for name, value in (
            ("AWS_REGION", config.region),
            ("AWS_DEFAULT_REGION", config.region),
            ("IMAGE_REGISTRY", config.image_registry),
            ("SSM_PARAMETER_PATH", config.app_parameter_path),
        )
    )
    return [
        "set -eu",
        f"mkdir -p {path}",
        f"aws s3 cp --recursive --only-show-errors {source} {path}/",
        f"cd {path}",
        f"export {exports}",
        f"bash remote-deploy.sh {shlex.quote(action)} {shlex.quote(image_tag)}",
    ]


def run_on_instance(
    ssm: SSMClient,
    config: DeployConfig,
    commands: Sequence[str],
    *,
    comment: str,
    timeout_seconds: int = 1800,
    poll_seconds: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> CommandResult:
    """Run `commands` on the app host through SSM and wait for them to finish."""
    response = ssm.send_command(
        InstanceIds=[config.instance_id],
        DocumentName="AWS-RunShellScript",
        Comment=comment[:100],
        TimeoutSeconds=120,  # how long SSM may take to deliver it to the agent
        Parameters={
            "commands": list(commands),
            "executionTimeout": [str(timeout_seconds)],
        },
    )
    command_id = response["Command"]["CommandId"]
    print(f"ssm command {command_id} sent to {config.instance_id}")

    deadline = clock() + timeout_seconds + 120
    while True:
        sleep(poll_seconds)
        try:
            invocation = ssm.get_command_invocation(
                CommandId=command_id, InstanceId=config.instance_id
            )
        except ClientError as error:
            # Briefly true right after send_command; anything else is a real failure.
            if error.response.get("Error", {}).get("Code") != "InvocationDoesNotExist":
                raise
            invocation = None

        if invocation is not None and invocation["Status"] in TERMINAL_STATUSES:
            return CommandResult(
                command_id=command_id,
                status=invocation["Status"],
                stdout=invocation.get("StandardOutputContent", ""),
                stderr=invocation.get("StandardErrorContent", ""),
            )
        if clock() > deadline:
            raise DeployError(f"ssm command {command_id} did not finish in time")


def report(result: CommandResult) -> None:
    print("----- host output -----")
    print(result.stdout.rstrip() or "(no output)")
    if result.stderr.strip():
        print("----- host stderr -----")
        print(result.stderr.rstrip())
    print(f"----- {result.status} -----")


@dataclass(frozen=True, slots=True)
class Clients:
    ssm: SSMClient
    s3: S3Client
    rds: RDSClient

    @classmethod
    def create(cls, region: str | None) -> Clients:
        session = boto3.session.Session(region_name=region)
        return cls(ssm=session.client("ssm"), s3=session.client("s3"), rds=session.client("rds"))


def deploy(
    clients: Clients,
    environment: str,
    image_tag: str,
    *,
    skip_snapshot: bool = False,
    repo_root: Path = REPO_ROOT,
    sleep: Callable[[float], None] = time.sleep,
) -> CommandResult:
    validate_inputs(environment, image_tag)
    config = DeployConfig.load(clients.ssm, environment)
    upload_release(clients.s3, config, image_tag, repo_root)
    if skip_snapshot:
        print("::warning::skipping the pre-deploy database snapshot (--skip-snapshot)")
    else:
        snapshot_database(clients.rds, config, environment, image_tag)
    result = run_on_instance(
        clients.ssm,
        config,
        host_commands(config, "deploy", image_tag),
        comment=f"deploy {image_tag[:12]} to {environment}",
        sleep=sleep,
    )
    report(result)
    return result


def rollback(
    clients: Clients,
    environment: str,
    image_tag: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> CommandResult:
    validate_inputs(environment, image_tag)
    config = DeployConfig.load(clients.ssm, environment)
    result = run_on_instance(
        clients.ssm,
        config,
        host_commands(config, "rollback", image_tag),
        comment=f"rollback {image_tag[:12]} on {environment}",
        timeout_seconds=900,
        sleep=sleep,
    )
    report(result)
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy to or roll back an AWS environment.")
    parser.add_argument("action", choices=["deploy", "rollback"])
    parser.add_argument("--environment", required=True, help="staging or production")
    parser.add_argument("--image-tag", required=True, help="full commit SHA of the images")
    parser.add_argument("--region", default=None, help="defaults to AWS_REGION")
    parser.add_argument(
        "--skip-snapshot",
        action="store_true",
        help="deploy without the pre-deploy RDS snapshot (emergencies only)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    clients = Clients.create(args.region)
    try:
        if args.action == "deploy":
            result = deploy(
                clients, args.environment, args.image_tag, skip_snapshot=args.skip_snapshot
            )
        else:
            result = rollback(clients, args.environment, args.image_tag)
    except DeployError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    return 0 if result.succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
