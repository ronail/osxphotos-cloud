"""Tests for the osxphotos cloud push/pull commands (osxphotos.cli.cloud)."""

from __future__ import annotations

import subprocess

import click
import pytest
from click.testing import CliRunner

from osxphotos.cli.cloud import cloud_cli, rclone_sync
from osxphotos.platform import is_macos

pytestmark = pytest.mark.skipif(not is_macos, reason="cloud commands require macOS")

# bundled test library (14 photos) that osxphotos ships with
TEST_LIBRARY = "tests/Test-15.4.1.photoslibrary"
REMOTE = "testremote:backup"


def test_cloud_group_is_registered_with_main_cli():
    """`cloud` (with push/pull) is wired into the main osxphotos CLI."""
    from osxphotos.cli.cli import cli_main

    assert "cloud" in cli_main.commands
    assert set(cli_main.commands["cloud"].commands) >= {"push", "pull"}


def test_push_exports_date_tree_then_syncs_remote(tmp_path, monkeypatch):
    """push exports into a YYYY/MM/DD tree, then syncs the staging dir to the remote."""
    staging = tmp_path / "staging"
    sync_calls = []

    def fake_rclone_sync(source, dest, **kwargs):
        sync_calls.append((source, dest, kwargs))

    monkeypatch.setattr("osxphotos.cli.cloud.rclone_sync", fake_rclone_sync)

    result = CliRunner().invoke(
        cloud_cli,
        [
            "push",
            REMOTE,
            "--staging-dir",
            str(staging),
            "--db",
            TEST_LIBRARY,
            "--no-progress",
        ],
    )

    assert result.exit_code == 0, result.output
    # files were exported using the default {created.year}/{created.mm}/{created.dd} template
    dated = sorted(staging.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9]/*"))
    assert dated, f"no YYYY/MM/DD files exported: {sorted(staging.rglob('*'))}"
    # export database is written for incremental runs and travels with the sync
    assert (staging / ".osxphotos_export.db").exists()
    # exactly one rclone sync: staging -> remote
    assert len(sync_calls) == 1
    source, dest, _kwargs = sync_calls[0]
    assert source == str(staging)
    assert dest == REMOTE


def test_push_reports_export_failure_and_does_not_sync(tmp_path, monkeypatch):
    """A non-zero export return code aborts push before rclone runs."""
    called = []
    monkeypatch.setattr(
        "osxphotos.cli.cloud.rclone_sync", lambda *a, **k: called.append(a)
    )

    result = CliRunner().invoke(
        cloud_cli,
        [
            "push",
            REMOTE,
            "--staging-dir",
            str(tmp_path / "staging"),
            "--db",
            "/nonexistent/library.photoslibrary",
            "--no-progress",
        ],
    )

    assert result.exit_code != 0
    assert not called


def test_pull_syncs_then_imports_with_skip_dups(tmp_path, monkeypatch):
    """pull downloads the remote, then imports the restore dir into Photos."""
    restore = tmp_path / "restore"
    sync_calls = []
    import_calls = []

    monkeypatch.setattr(
        "osxphotos.cli.cloud.rclone_sync",
        lambda *a, **k: sync_calls.append((a, k)),
    )
    monkeypatch.setattr(
        "osxphotos.cli.cloud.import_cli",
        lambda **k: import_calls.append(k),
    )

    result = CliRunner().invoke(
        cloud_cli,
        ["pull", REMOTE, "--restore-dir", str(restore), "--no-progress"],
    )

    assert result.exit_code == 0, result.output
    assert sync_calls and sync_calls[0][0] == (REMOTE, str(restore))
    assert len(import_calls) == 1
    assert import_calls[0]["files_or_dirs"] == (str(restore),)
    assert import_calls[0]["skip_dups"] is True
    assert import_calls[0]["walk"] is True


def test_pull_dry_run_skips_import(tmp_path, monkeypatch):
    """--dry-run downloads nothing for real and never imports."""
    import_calls = []
    monkeypatch.setattr("osxphotos.cli.cloud.rclone_sync", lambda *a, **k: None)
    monkeypatch.setattr(
        "osxphotos.cli.cloud.import_cli", lambda **k: import_calls.append(k)
    )

    result = CliRunner().invoke(
        cloud_cli,
        ["pull", REMOTE, "--restore-dir", str(tmp_path / "restore"), "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert import_calls == []


def test_rclone_sync_builds_sync_command(monkeypatch):
    """rclone_sync runs `rclone sync SRC DEST --progress`."""
    captured = {}
    monkeypatch.setattr("osxphotos.cli.cloud.rclone_installed", lambda: True)

    def fake_run(args, check):
        captured["args"] = args
        captured["check"] = check

    monkeypatch.setattr("osxphotos.cli.cloud.subprocess.run", fake_run)

    rclone_sync("/src", "remote:dst")

    assert captured["args"] == ["rclone", "sync", "/src", "remote:dst", "--progress"]
    assert captured["check"] is True


def test_rclone_sync_dry_run_adds_flag_and_extra_args(monkeypatch):
    """--dry-run and pass-through rclone args are appended to the command."""
    captured = {}
    monkeypatch.setattr("osxphotos.cli.cloud.rclone_installed", lambda: True)
    monkeypatch.setattr(
        "osxphotos.cli.cloud.subprocess.run",
        lambda args, check: captured.setdefault("args", args),
    )

    rclone_sync("/src", "remote:dst", dry_run=True, extra_args=("--transfers", "4"))

    assert "--dry-run" in captured["args"]
    assert captured["args"][-2:] == ["--transfers", "4"]


def test_rclone_sync_missing_binary_raises_click_exception(monkeypatch):
    """A clear error is raised when rclone is not installed."""
    monkeypatch.setattr("osxphotos.cli.cloud.rclone_installed", lambda: False)

    with pytest.raises(click.ClickException):
        rclone_sync("/src", "remote:dst")


def test_rclone_sync_failure_raises_click_exception(monkeypatch):
    """A non-zero rclone exit is surfaced as a ClickException."""
    monkeypatch.setattr("osxphotos.cli.cloud.rclone_installed", lambda: True)

    def boom(args, check):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr("osxphotos.cli.cloud.subprocess.run", boom)

    with pytest.raises(click.ClickException):
        rclone_sync("/src", "remote:dst")
