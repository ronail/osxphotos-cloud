"""Tests for the osxphotos cloud S3 convenience commands (osxphotos.cli.cloud_s3)."""

from __future__ import annotations

import subprocess

import click
import pytest
from click.testing import CliRunner

from osxphotos.cli.cloud import cloud_cli
from osxphotos.platform import is_macos

pytestmark = pytest.mark.skipif(not is_macos, reason="cloud S3 commands require macOS")

# bundled test library that osxphotos ships with
TEST_LIBRARY = "tests/Test-15.4.1.photoslibrary"
REMOTE = "testremote:backup"


def test_s3_commands_are_registered_under_cloud_group():
    """s3-push, s3-pull, s3-configure are wired into the cloud command group."""
    from osxphotos.cli.cli import cli_main

    cloud = cli_main.commands.get("cloud")
    assert cloud is not None
    assert set(cloud.commands) >= {"s3-push", "s3-pull", "s3-configure"}


def test_s3_push_builds_remote_and_delegates_to_push(tmp_path, monkeypatch):
    """s3-push constructs the rclone remote string and invokes push."""
    called = {}

    def fake_push(remote, **kwargs):
        called["remote"] = remote
        called["kwargs"] = kwargs
        return 0

    monkeypatch.setattr("osxphotos.cli.cloud_s3.cloud_push", fake_push)
    monkeypatch.setattr("osxphotos.cli.cloud_s3.rclone_installed", lambda: True)

    result = CliRunner().invoke(
        cloud_cli,
        [
            "s3-push",
            "--bucket",
            "my-bucket",
            "--region",
            "us-east-1",
            "--prefix",
            "photos",
            "--staging-dir",
            str(tmp_path / "staging"),
            "--db",
            TEST_LIBRARY,
            "--no-progress",
        ],
    )

    assert result.exit_code == 0, result.output
    assert called["remote"] == "s3:my-bucket/photos"
    assert called["kwargs"]["staging_dir"].endswith("staging")
    assert called["kwargs"]["no_progress"] is True


def test_s3_push_with_profile_and_endpoint(tmp_path, monkeypatch):
    """s3-push supports --profile and --endpoint-url for non-AWS S3."""
    called = {}

    def fake_push(remote, **kwargs):
        called["remote"] = remote

    monkeypatch.setattr("osxphotos.cli.cloud_s3.cloud_push", fake_push)
    monkeypatch.setattr("osxphotos.cli.cloud_s3.rclone_installed", lambda: True)

    result = CliRunner().invoke(
        cloud_cli,
        [
            "s3-push",
            "--bucket",
            "my-bucket",
            "--region",
            "us-west-2",
            "--profile",
            "myprofile",
            "--endpoint-url",
            "https://s3.example.com",
            "--staging-dir",
            str(tmp_path / "staging"),
            "--no-progress",
        ],
    )

    assert result.exit_code == 0, result.output
    # remote string is just s3:bucket; profile/endpoint are in rclone config
    assert called["remote"] == "s3:my-bucket"


def test_s3_pull_builds_remote_and_delegates_to_pull(tmp_path, monkeypatch):
    """s3-pull constructs the rclone remote string and invokes pull."""
    called = {}

    def fake_pull(remote, **kwargs):
        called["remote"] = remote
        called["kwargs"] = kwargs
        return 0

    monkeypatch.setattr("osxphotos.cli.cloud_s3.cloud_pull", fake_pull)
    monkeypatch.setattr("osxphotos.cli.cloud_s3.rclone_installed", lambda: True)

    result = CliRunner().invoke(
        cloud_cli,
        [
            "s3-pull",
            "--bucket",
            "my-bucket",
            "--region",
            "eu-west-1",
            "--restore-dir",
            str(tmp_path / "restore"),
            "--no-progress",
        ],
    )

    assert result.exit_code == 0, result.output
    assert called["remote"] == "s3:my-bucket"
    assert called["kwargs"]["restore_dir"].endswith("restore")


def test_s3_configure_creates_rclone_remote(monkeypatch):
    """s3-configure runs `rclone config create` with S3 parameters."""
    calls = []
    monkeypatch.setattr(
        "osxphotos.cli.cloud_s3.subprocess.run",
        lambda *a, **k: calls.append({"args": a[0], "check": k.get("check")}),
    )
    monkeypatch.setattr("osxphotos.cli.cloud_s3.rclone_installed", lambda: True)

    result = CliRunner().invoke(
        cloud_cli,
        [
            "s3-configure",
            "myremote",
            "--bucket",
            "my-bucket",
            "--region",
            "us-east-1",
            "--access-key-id",
            "AKIA...",
            "--secret-access-key",
            "SECRET",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    args = calls[0]["args"]
    assert args[:3] == ["rclone", "config", "create"]
    assert args[3] == "myremote"
    assert args[4] == "s3"
    # provider and region present (rclone uses --provider=VALUE format)
    assert any(a.startswith("--provider=") for a in args)
    assert any(a.startswith("--region=") for a in args)
    # env_auth is false by default, so access keys should be present
    assert any(a.startswith("--access-key-id=") for a in args)
    assert any(a.startswith("--secret-access-key=") for a in args)


def test_s3_configure_rejects_missing_credentials(monkeypatch):
    """s3-configure requires credentials unless --env-auth is used."""
    monkeypatch.setattr("osxphotos.cli.cloud_s3.rclone_installed", lambda: True)
    monkeypatch.setattr("osxphotos.cli.cloud_s3.subprocess.run", lambda *a, **k: None)

    result = CliRunner().invoke(
        cloud_cli,
        [
            "s3-configure",
            "myremote",
            "--bucket",
            "my-bucket",
            "--region",
            "us-east-1",
        ],
    )

    assert result.exit_code != 0
    assert (
        "credentials" in result.output.lower() or "access-key" in result.output.lower()
    )


def test_s3_commands_require_macos():
    """S3 commands are only available on macOS (like the rest of cloud)."""
    from osxphotos.platform import is_macos

    if not is_macos:
        # On non-macOS, the cloud group exists but S3 commands should not be registered
        from osxphotos.cli.cli import cli_main

        cloud = cli_main.commands.get("cloud")
        if cloud:
            assert "s3-push" not in cloud.commands
            assert "s3-pull" not in cloud.commands
    else:
        # On macOS, they should be registered
        from osxphotos.cli.cli import cli_main

        cloud = cli_main.commands.get("cloud")
        assert cloud is not None
        assert "s3-push" in cloud.commands
        assert "s3-pull" in cloud.commands
