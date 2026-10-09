"""Install/extract a native package and exercise its installed executable."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from build_installers import ROOT, run, smoke


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", type=Path, default=ROOT / "release")
    args = parser.parse_args()
    packages = args.packages.resolve()
    report = ROOT / "build/installed-selftest.json"
    with tempfile.TemporaryDirectory(prefix="Doupi install test ") as directory:
        directory = Path(directory)
        if sys.platform == "win32":
            installer, = packages.glob("*-setup.exe")
            destination = directory / "Installed Doupi"
            run(installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", f"/DIR={destination}", timeout=180)
            try:
                smoke(destination / "Doupi.exe", report)
            finally:
                run(destination / "unins000.exe", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", timeout=180)
        elif sys.platform == "darwin":
            installer, = packages.glob("*.dmg")
            mount = directory / "volume"
            mount.mkdir()
            run("hdiutil", "verify", installer)
            run("hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", mount, installer)
            try:
                destination = directory / "Applications/豆皮.app"
                run("ditto", mount / "豆皮.app", destination)
                run("codesign", "--verify", "--deep", "--strict", destination)
                smoke(destination / "Contents/MacOS/Doupi", report)
            finally:
                run("hdiutil", "detach", mount)
        elif sys.platform.startswith("linux"):
            installer, = packages.glob("*.deb")
            # CI runners are disposable; dependency installation occurs beforehand.
            run("sudo", "dpkg", "--install", installer)
            try:
                smoke(Path("/usr/bin/doupi"), report)
                run("desktop-file-validate", "/usr/share/applications/doupi.desktop")
            finally:
                run("sudo", "dpkg", "--remove", "doupi")
        else:
            parser.error("Unsupported operating system")
    print("Installed package verified:", json.loads(report.read_text())["checks"])


if __name__ == "__main__":
    main()
