"""Cloud sync commands for osxphotos.

Adds ``osxphotos cloud push`` and ``osxphotos cloud pull`` which mirror a Photos
library to and from any remote configured in `rclone <https://rclone.org>`_.

Photos are staged in a human-readable ``YYYY/MM/DD`` directory tree so the
remote is browsable without osxphotos, while ``osxphotos``' own export database
travels with the sync so that repeat runs only transfer new or changed files.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence

import click

from osxphotos._constants import OSXPHOTOS_EXPORT_DB
from osxphotos.platform import assert_macos

# cloud sync is built on `osxphotos export` / `osxphotos import`, both macOS only
assert_macos()

from .export import export_cli
from .import_cli import import_cli

#: default local staging directory used by ``cloud push``
DEFAULT_STAGING_DIR = os.path.join("~", "Pictures", "CloudSyncStaging")

#: default local download directory used by ``cloud pull``
DEFAULT_RESTORE_DIR = os.path.join("~", "Pictures", "DownloadedPhotos")

#: template that organizes exported files as YEAR/MONTH/DAY/filename.ext
DEFAULT_DIRECTORY_TEMPLATE = "{created.year}/{created.mm}/{created.dd}"

#: name of the rclone executable
RCLONE = "rclone"


def rclone_installed() -> bool:
    """Return True if the ``rclone`` executable is available on PATH."""
    return shutil.which(RCLONE) is not None


def rclone_sync(
    source: str,
    dest: str,
    *,
    dry_run: bool = False,
    progress: bool = True,
    extra_args: Sequence[str] = (),
) -> None:
    """Mirror ``source`` to ``dest`` with ``rclone sync``.

    Args:
        source: local path or rclone remote path to copy from
        dest: local path or rclone remote path to copy to
        dry_run: if True, pass ``--dry-run`` so rclone reports planned work only
        progress: if True, pass ``--progress`` to show transfer progress
        extra_args: additional arguments appended to the rclone command line

    Raises:
        click.ClickException: if rclone is not installed or exits non-zero
    """
    if not rclone_installed():
        raise click.ClickException(
            f"'{RCLONE}' was not found on your PATH. Install rclone "
            "(https://rclone.org/install/) and configure the remote with "
            "`rclone config` before running this command."
        )

    args = [RCLONE, "sync", source, dest]
    if progress and not dry_run:
        args.append("--progress")
    if dry_run:
        args.append("--dry-run")
    args.extend(extra_args)

    try:
        subprocess.run(args, check=True)
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(
            f"rclone sync failed with exit code {exc.returncode}"
        ) from exc


@click.group(name="cloud")
def cloud_cli():
    """Sync the Photos library to/from cloud storage using rclone.

    \b
    Examples:
        osxphotos cloud push myremote:photos
        osxphotos cloud pull myremote:photos
    """


@cloud_cli.command(name="push")
@click.argument("remote")
@click.option(
    "--staging-dir",
    default=DEFAULT_STAGING_DIR,
    show_default=True,
    metavar="DIRECTORY",
    type=click.Path(file_okay=False),
    help="Local staging directory for the exported YEAR/MONTH/DAY tree.",
)
@click.option(
    "--directory",
    "directory_template",
    default=DEFAULT_DIRECTORY_TEMPLATE,
    show_default=True,
    metavar="TEMPLATE",
    help="Template for the exported directory structure.",
)
@click.option(
    "--db",
    "db",
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
    "--rclone-arg",
    "rclone_args",
    multiple=True,
    metavar="ARG",
    help="Additional argument to pass to rclone; may be specified multiple times.",
)
@click.option(
    "-V",
    "--verbose",
    count=True,
    help="Print verbose output; may be specified multiple times for more verbose output.",
)
def push(
    remote,
    staging_dir,
    directory_template,
    db,
    dry_run,
    no_progress,
    rclone_args,
    verbose,
):
    """Export photos to a YEAR/MONTH/DAY tree and sync them to rclone REMOTE.

    REMOTE is any destination accepted by rclone, e.g. ``s3:bucket/photos`` or
    ``b2:photos-backup``. Only new or updated files are exported on subsequent
    runs (via osxphotos' export database) and only changes are transferred.
    """
    staging_dir = os.path.abspath(os.path.expanduser(staging_dir))
    os.makedirs(staging_dir, exist_ok=True)

    click.echo(f"Exporting photos to staging directory: {staging_dir}")
    return_code = export_cli(
        dest=staging_dir,
        db=db,
        directory=directory_template,
        update=True,
        dry_run=dry_run,
        no_progress=no_progress,
        verbose_flag=bool(verbose),
    )
    if return_code:
        raise click.ClickException(f"export failed with return code {return_code}")

    if dry_run:
        click.echo("Dry run; skipping rclone sync.")
        return

    click.echo(f"Syncing staging directory to remote: {remote}")
    rclone_sync(
        staging_dir,
        remote,
        progress=not no_progress,
        extra_args=rclone_args,
    )
    click.echo("Cloud push complete.")


@cloud_cli.command(name="pull")
@click.argument("remote")
@click.option(
    "--restore-dir",
    default=DEFAULT_RESTORE_DIR,
    show_default=True,
    metavar="DIRECTORY",
    type=click.Path(file_okay=False),
    help="Local directory to download photos into before importing them.",
)
@click.option(
    "--library",
    "library",
    default=None,
    metavar="PHOTOS_LIBRARY_PATH",
    type=click.Path(exists=True),
    help="Path to the Photos library to import into. Defaults to the last opened library.",
)
@click.option(
    "--skip-dups/--no-skip-dups",
    default=True,
    show_default=True,
    help="Skip photos that already exist in the library.",
)
@click.option(
    "--exportdb",
    "exportdb",
    default=None,
    metavar="EXPORT_DB",
    help="osxphotos export database to use for duplicate/metadata matching. "
    "Defaults to the export database synced alongside the photos, if present.",
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
    "--rclone-arg",
    "rclone_args",
    multiple=True,
    metavar="ARG",
    help="Additional argument to pass to rclone; may be specified multiple times.",
)
@click.option(
    "-V",
    "--verbose",
    count=True,
    help="Print verbose output; may be specified multiple times for more verbose output.",
)
def pull(
    remote,
    restore_dir,
    library,
    skip_dups,
    exportdb,
    dry_run,
    no_progress,
    rclone_args,
    verbose,
):
    """Download new photos from rclone REMOTE and import them into Photos.

    REMOTE is any source accepted by rclone, e.g. ``s3:bucket/photos``. Photos
    already present in the library are skipped when ``--skip-dups`` is used
    (the default), using the export database synced alongside the photos when
    available.
    """
    restore_dir = os.path.abspath(os.path.expanduser(restore_dir))
    os.makedirs(restore_dir, exist_ok=True)

    click.echo(f"Downloading from remote to restore directory: {restore_dir}")
    rclone_sync(
        remote,
        restore_dir,
        dry_run=dry_run,
        progress=not no_progress,
        extra_args=rclone_args,
    )

    if dry_run:
        click.echo("Dry run; skipping import.")
        return

    # use the export database synced with the photos (if any) for dedup/metadata
    exportdb = exportdb or os.path.join(restore_dir, OSXPHOTOS_EXPORT_DB)
    exportdb = exportdb if os.path.exists(exportdb) else None

    click.echo("Importing downloaded photos into Photos")
    import_cli(
        files_or_dirs=(restore_dir,),
        library=library,
        exportdb=exportdb,
        skip_dups=skip_dups,
        walk=True,
        no_progress=no_progress,
        verbose_flag=bool(verbose),
    )
    click.echo("Cloud pull complete.")
