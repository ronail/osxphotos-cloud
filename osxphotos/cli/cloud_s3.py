"""AWS S3 convenience commands for osxphotos cloud.

Provides `osxphotos cloud s3-push`, `osxphotos cloud s3-pull`, and
`osxphotos cloud s3-configure` which construct rclone S3 remote strings
and delegate to the core push/pull/configure machinery.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from collections.abc import Sequence

import click

from osxphotos.platform import assert_macos

assert_macos()

from .cloud import cloud_cli
from .cloud import pull as cloud_pull
from .cloud import push as cloud_push

RCLONE = "rclone"


def rclone_installed() -> bool:
    """Return True if the ``rclone`` executable is available on PATH."""
    return shutil.which(RCLONE) is not None


def _build_s3_remote(
    bucket: str,
    prefix: str | None = None,
    region: str = "us-east-1",
    profile: str | None = None,
    endpoint_url: str | None = None,
    provider: str = "AWS",
) -> str:
    """Build an rclone S3 remote string.

    rclone S3 remote format: s3:bucket/path
    Provider-specific options are passed via rclone config, not the remote string.
    """
    path = bucket
    if prefix:
        path = f"{bucket}/{prefix.strip('/')}"
    return f"s3:{path}"


def _build_rclone_config_args(
    name: str,
    bucket: str,
    region: str,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    profile: str | None = None,
    endpoint_url: str | None = None,
    provider: str = "AWS",
    env_auth: bool = False,
    no_check_bucket: bool = True,
) -> list[str]:
    """Build arguments for `rclone config create name s3 ...`."""
    args = [
        "rclone",
        "config",
        "create",
        name,
        "s3",
        f"--provider={provider}",
        f"--region={region}",
        f"--bucket={bucket}",
    ]
    if no_check_bucket:
        args.append("--no-check-bucket=true")

    if env_auth:
        args.append("--env-auth=true")
    else:
        if not access_key_id or not secret_access_key:
            raise click.ClickException(
                "S3 credentials required: provide --access-key-id and --secret-access-key "
                "or use --env-auth to pick up credentials from environment/instance profile."
            )
        args.append(f"--access-key-id={access_key_id}")
        args.append(f"--secret-access-key={secret_access_key}")

    if profile:
        args.append(f"--profile={profile}")
    if endpoint_url:
        args.append(f"--endpoint={endpoint_url}")

    return args


@cloud_cli.command(name="s3-push")
@click.option(
    "--bucket",
    required=True,
    metavar="BUCKET",
    help="S3 bucket name.",
)
@click.option(
    "--prefix",
    default=None,
    metavar="PREFIX",
    help="Optional key prefix (folder) within the bucket.",
)
@click.option(
    "--region",
    default="us-east-1",
    show_default=True,
    metavar="REGION",
    help="AWS region.",
)
@click.option(
    "--profile",
    default=None,
    metavar="PROFILE",
    help="AWS CLI profile to use (stored in rclone config).",
)
@click.option(
    "--endpoint-url",
    default=None,
    metavar="URL",
    help="Custom S3 endpoint (for S3-compatible services like MinIO, Cloudflare R2).",
)
@click.option(
    "--provider",
    default="AWS",
    show_default=True,
    metavar="PROVIDER",
    type=click.Choice(
        [
            "AWS",
            "Ceph",
            "DigitalOcean",
            "Dreamhost",
            "IBM COS",
            "MinIO",
            "Wasabi",
            "Other",
        ]
    ),
    help="S3 provider type.",
)
# forward options to underlying push command
@click.option(
    "--staging-dir",
    default=None,
    metavar="DIRECTORY",
    help="Local staging directory for the exported YEAR/MONTH/DAY tree.",
)
@click.option(
    "--db",
    default=None,
    metavar="PHOTOS_LIBRARY_PATH",
    type=click.Path(exists=True),
    help="Path to the Photos library to export. Defaults to the last opened library.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Export and sync in dry-run mode; no files are written and no data is transferred.",
)
@click.option(
    "--no-progress",
    is_flag=True,
    help="Do not display progress bars during export or sync.",
)
@click.option(
    "-V",
    "--verbose",
    count=True,
    help="Print verbose output; may be specified multiple times for more verbose output.",
)
@click.pass_context
def s3_push(
    ctx,
    bucket,
    prefix,
    region,
    profile,
    endpoint_url,
    provider,
    staging_dir,
    db,
    dry_run,
    no_progress,
    verbose,
):
    """Push photos to an S3 bucket via rclone.

    Constructs an rclone S3 remote string and delegates to `osxphotos cloud push`.

    Examples:
        osxphotos cloud s3-push --bucket my-photos --region us-east-1
        osxphotos cloud s3-push --bucket my-bucket --prefix photos/2024 --profile myprofile
        osxphotos cloud s3-push --bucket my-bucket --endpoint-url https://s3.example.com --provider MinIO
    """
    remote = _build_s3_remote(bucket, prefix, region, profile, endpoint_url, provider)
    # delegate to the core push command, preserving other options
    ctx.invoke(
        cloud_push,
        remote=remote,
        staging_dir=staging_dir,
        db=db,
        dry_run=dry_run,
        no_progress=no_progress,
        verbose=verbose,
    )


@cloud_cli.command(name="s3-pull")
@click.option(
    "--bucket",
    required=True,
    metavar="BUCKET",
    help="S3 bucket name.",
)
@click.option(
    "--prefix",
    default=None,
    metavar="PREFIX",
    help="Optional key prefix (folder) within the bucket.",
)
@click.option(
    "--region",
    default="us-east-1",
    show_default=True,
    metavar="REGION",
    help="AWS region.",
)
@click.option(
    "--profile",
    default=None,
    metavar="PROFILE",
    help="AWS CLI profile to use (stored in rclone config).",
)
@click.option(
    "--endpoint-url",
    default=None,
    metavar="URL",
    help="Custom S3 endpoint (for S3-compatible services like MinIO, Cloudflare R2).",
)
@click.option(
    "--provider",
    default="AWS",
    show_default=True,
    metavar="PROVIDER",
    type=click.Choice(
        [
            "AWS",
            "Ceph",
            "DigitalOcean",
            "Dreamhost",
            "IBM COS",
            "MinIO",
            "Wasabi",
            "Other",
        ]
    ),
    help="S3 provider type.",
)
# forward options to underlying pull command
@click.option(
    "--restore-dir",
    default=None,
    metavar="DIRECTORY",
    help="Local directory to download photos into before importing them.",
)
@click.option(
    "--library",
    default=None,
    metavar="PHOTOS_LIBRARY_PATH",
    type=click.Path(exists=True),
    help="Path to the Photos library to import into. Defaults to the last opened library.",
)
@click.option(
    "--skip-dups/--no-skip-dups",
    default=True,
    help="Skip photos that already exist in the library.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Download in dry-run mode; no files are transferred and nothing is imported.",
)
@click.option(
    "--no-progress",
    is_flag=True,
    help="Do not display progress bars during sync or import.",
)
@click.option(
    "-V",
    "--verbose",
    count=True,
    help="Print verbose output; may be specified multiple times for more verbose output.",
)
@click.pass_context
def s3_pull(
    ctx,
    bucket,
    prefix,
    region,
    profile,
    endpoint_url,
    provider,
    restore_dir,
    library,
    skip_dups,
    dry_run,
    no_progress,
    verbose,
):
    """Pull photos from an S3 bucket via rclone.

    Constructs an rclone S3 remote string and delegates to `osxphotos cloud pull`.

    Examples:
        osxphotos cloud s3-pull --bucket my-photos --region us-east-1
        osxphotos cloud s3-pull --bucket my-bucket --prefix photos/2024
    """
    remote = _build_s3_remote(bucket, prefix, region, profile, endpoint_url, provider)
    ctx.invoke(
        cloud_pull,
        remote=remote,
        restore_dir=restore_dir,
        library=library,
        skip_dups=skip_dups,
        dry_run=dry_run,
        no_progress=no_progress,
        verbose=verbose,
    )


@cloud_cli.command(name="s3-configure")
@click.argument("name")
@click.option(
    "--bucket",
    required=True,
    metavar="BUCKET",
    help="S3 bucket name.",
)
@click.option(
    "--region",
    default="us-east-1",
    show_default=True,
    metavar="REGION",
    help="AWS region.",
)
@click.option(
    "--access-key-id",
    default=None,
    metavar="KEY_ID",
    help="AWS access key ID.",
)
@click.option(
    "--secret-access-key",
    default=None,
    metavar="SECRET_KEY",
    help="AWS secret access key.",
)
@click.option(
    "--env-auth",
    is_flag=True,
    help="Use environment/instance profile credentials instead of explicit keys.",
)
@click.option(
    "--profile",
    default=None,
    metavar="PROFILE",
    help="AWS CLI profile name to store in rclone config.",
)
@click.option(
    "--endpoint-url",
    default=None,
    metavar="URL",
    help="Custom S3 endpoint (for S3-compatible services).",
)
@click.option(
    "--provider",
    default="AWS",
    show_default=True,
    metavar="PROVIDER",
    type=click.Choice(
        [
            "AWS",
            "Ceph",
            "DigitalOcean",
            "Dreamhost",
            "IBM COS",
            "MinIO",
            "Wasabi",
            "Other",
        ]
    ),
    help="S3 provider type.",
)
def s3_configure(
    name,
    bucket,
    region,
    access_key_id,
    secret_access_key,
    env_auth,
    profile,
    endpoint_url,
    provider,
):
    """Create or update an rclone S3 remote.

    Configures an rclone remote with S3 provider settings so it can be used
    with `osxphotos cloud push/pull` or directly with rclone.

    Examples:
        osxphotos cloud s3-configure myremote --bucket my-bucket --region us-east-1 \\
            --access-key-id AKIA... --secret-access-key SECRET
        osxphotos cloud s3-configure myremote --bucket my-bucket --region us-east-1 --env-auth
    """
    if not rclone_installed():
        raise click.ClickException(
            "'rclone' was not found on your PATH. Install rclone "
            "(https://rclone.org/install/) first."
        )

    args = _build_rclone_config_args(
        name=name,
        bucket=bucket,
        region=region,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        profile=profile,
        endpoint_url=endpoint_url,
        provider=provider,
        env_auth=env_auth,
    )

    click.echo(f"Creating rclone S3 remote '{name}'...")
    try:
        subprocess.run(args, check=True)
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(
            f"rclone config create failed with exit code {exc.returncode}"
        ) from exc

    click.echo(f"Remote '{name}' configured. Use it with:")
    click.echo(f"  osxphotos cloud push {name}:")
    click.echo(f"  osxphotos cloud pull {name}:")
