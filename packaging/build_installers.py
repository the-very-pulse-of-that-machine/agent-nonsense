"""Build native, self-contained installers on the current operating system."""
import argparse
import hashlib
from importlib.metadata import version as package_version
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run(*command, **kwargs):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), check=True, **kwargs)


def smoke(executable, report):
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    run(executable, "--self-test", report, env=environment, timeout=120)
    result = json.loads(report.read_text(encoding="utf-8"))
    if not result.get("ok"):
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    print(json.dumps(result, ensure_ascii=False), flush=True)


def make_icons(assets):
    from PIL import Image
    assets.mkdir(parents=True, exist_ok=True)
    original = ROOT / "agent_nonsense/desktop/assets/agent-nonsense.ico"
    shutil.copy2(original, assets / "doupi.ico")
    with Image.open(original) as image:
        rgba = image.convert("RGBA")
        rgba.resize((256, 256), Image.Resampling.LANCZOS).save(assets / "doupi.png")
        if sys.platform == "darwin":
            rgba.resize((1024, 1024), Image.Resampling.LANCZOS).save(assets / "doupi.icns")


def windows(bundle, output, version, arch):
    if arch != "x64":
        raise RuntimeError("The Windows installer currently targets x64")
    source = bundle / "Doupi"
    smoke(source / "Doupi.exe", output / "windows-x64-selftest.json")
    compiler = shutil.which("ISCC.exe") or shutil.which("iscc")
    if not compiler:
        candidate = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6/ISCC.exe"
        if candidate.is_file():
            compiler = str(candidate)
    if not compiler:
        raise RuntimeError("Install Inno Setup 6 (ISCC.exe) before building Windows installers")
    run(compiler, f"/DAppVersion={version}", f"/DSourceDir={source}", f"/DOutputPath={output}", ROOT / "packaging/windows.iss")
    archive = output / f"Doupi-{version}-windows-{arch}-portable.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as target:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                target.write(path, Path("Doupi") / path.relative_to(source))


def macos(bundle, output, version, arch):
    app = bundle / "豆皮.app"
    smoke(app / "Contents/MacOS/Doupi", output / f"macos-{arch}-selftest.json")
    run("codesign", "--verify", "--deep", "--strict", app)
    stage = ROOT / "build/dmg-stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    run("ditto", app, stage / "豆皮.app")
    (stage / "Applications").symlink_to("/Applications")
    shutil.copy2(ROOT / "packaging/INSTALL.txt", stage / "安装说明.txt")
    name = f"Doupi-{version}-macos-{arch}"
    run("hdiutil", "create", "-volname", "豆皮", "-srcfolder", stage,
        "-format", "UDZO", "-ov", output / (name + ".dmg"))
    run("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, output / (name + ".zip"))


def linux(bundle, output, version, arch, assets):
    source = bundle / "Doupi"
    smoke(source / "Doupi", output / f"linux-{arch}-selftest.json")
    with tarfile.open(output / f"Doupi-{version}-linux-{arch}.tar.gz", "w:gz") as archive:
        archive.add(source, arcname="Doupi")
    stage = ROOT / "build/deb-stage"
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(source, stage / "opt/doupi", symlinks=True)
    (stage / "DEBIAN").mkdir()
    deb_arch = {"x64": "amd64", "arm64": "arm64"}[arch]
    size = sum(path.stat().st_size for path in source.rglob("*") if path.is_file()) // 1024
    control = f"""Package: doupi
Version: {version}
Section: devel
Priority: optional
Architecture: {deb_arch}
Maintainer: Agent Nonsense contributors <noreply@github.com>
Installed-Size: {size}
Depends: libc6 (>= 2.35), libglib2.0-0, libgl1, libegl1, libfontconfig1, libdbus-1-3, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-keysyms1, libxcb-shape0, libxcb-xinerama0, libxcb-xkb1
Recommends: fonts-noto-cjk
Homepage: https://github.com/wahahaha-cpu/agent-nonsense
Description: Doupi local agent desktop workbench
 Self-contained Python/Qt GUI with local zero-token API streaming.
"""
    (stage / "DEBIAN/control").write_text(control, encoding="utf-8")
    launcher = stage / "usr/bin/doupi"
    launcher.parent.mkdir(parents=True)
    launcher.write_text('#!/bin/sh\nexec /opt/doupi/Doupi "$@"\n', encoding="utf-8")
    launcher.chmod(0o755)
    for source_file, destination in (
        (ROOT / "packaging/doupi.desktop", "usr/share/applications/doupi.desktop"),
        (assets / "doupi.png", "usr/share/icons/hicolor/256x256/apps/doupi.png"),
        (ROOT / "LICENSE", "usr/share/doc/doupi/copyright"),
        (ROOT / "packaging/THIRD_PARTY_NOTICES.md", "usr/share/doc/doupi/THIRD_PARTY_NOTICES.md"),
    ):
        destination = stage / destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination)
    run("desktop-file-validate", stage / "usr/share/applications/doupi.desktop")
    run("dpkg-deb", "--root-owner-group", "--build", stage, output / f"doupi_{version}_{deb_arch}.deb")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "release")
    parser.add_argument("--version", default=tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"])
    args = parser.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        parser.error("--version must have the form X.Y.Z")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error("Use an empty output directory to avoid mixing releases")
    machine = platform.machine().lower()
    arch = {"arm64": "arm64", "aarch64": "arm64", "amd64": "x64", "x86_64": "x64"}.get(machine)
    if not arch:
        parser.error("Unsupported architecture: " + machine)
    assets = ROOT / "build/installer-assets"
    make_icons(assets)
    bundle = ROOT / "build/frozen"
    environment = dict(os.environ, DOUPI_BUILD_VERSION=args.version)
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", bundle,
        "--workpath", ROOT / "build/pyinstaller", ROOT / "packaging/doupi.spec", cwd=ROOT, env=environment)
    if sys.platform == "win32":
        windows(bundle, output, args.version, arch)
    elif sys.platform == "darwin":
        macos(bundle, output, args.version, arch)
    elif sys.platform.startswith("linux"):
        linux(bundle, output, args.version, arch, assets)
    else:
        parser.error("Unsupported operating system: " + sys.platform)
    info = {
        "version": args.version, "platform": sys.platform, "architecture": arch,
        "python": platform.python_version(),
        "dependencies": {name: package_version(name) for name in ("PyInstaller", "PySide6-Essentials", "shiboken6")},
        "commit": os.environ.get("GITHUB_SHA") or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "signed": False,
    }
    (output / f"{sys.platform}-{arch}-BUILD-INFO.json").write_text(json.dumps(info, indent=2) + "\n")
    checksums = []
    for path in sorted(output.iterdir()):
        if path.is_file():
            with path.open("rb") as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            checksums.append(f"{checksum}  {path.name}")
    (output / f"{sys.platform}-{arch}-SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
