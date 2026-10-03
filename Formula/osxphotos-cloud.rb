# Homebrew formula for the `osxphotos-cloud` fork.
#
# Tap and install with:
#
#   brew tap ronail/osxphotos-cloud https://github.com/ronail/osxphotos-cloud
#   brew install osxphotos-cloud
#
class OsxphotosCloud < Formula
  include Language::Python::Virtualenv

  desc "Python app and library for Apple Photos with rclone cloud sync"
  homepage "https://github.com/ronail/osxphotos-cloud"
  url "https://github.com/ronail/osxphotos-cloud.git",
      revision: "6c17d20e6a3db482e64d12576104046156f8c07f"
  version "0.77.2-cloud"
  license "MIT"

  # Prefer an immutable release tarball once a tag exists, e.g. v0.77.2-cloud:
  #
  #   url "https://github.com/ronail/osxphotos-cloud/archive/refs/tags/v0.77.2-cloud.tar.gz"
  #   sha256 "<output of: curl -L <url> | shasum -a 256>"
  #
  # This formula currently declares no `resource` stanzas, so its Python
  # dependencies are resolved from PyPI when the formula is built. For a
  # hermetic, reproducible build run `brew update-python-resources
  # Formula/osxphotos-cloud.rb` (or copy the resource blocks from the upstream
  # `RhetTbull/osxphotos` tap formula) and commit the result before
  # distributing.

  depends_on "python@3.12"
  depends_on "rclone"

  def install
    virtualenv_install_with_resources
    # the entry point is installed as `osxphotos`; also expose it under the
    # fork's name so the cloud commands are easy to discover
    bin.install_symlink libexec/"bin/osxphotos" => "osxphotos-cloud"
  end

  test do
    assert_match "cloud", shell_output("#{bin}/osxphotos-cloud --help")
  end
end
