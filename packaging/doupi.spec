# Build on the target OS with Python 3.12 and packaging/requirements.txt.
import os
from pathlib import Path
import sys
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH).parent
assets = root / "build" / "installer-assets"
version = os.environ["DOUPI_BUILD_VERSION"]
icon = str(assets / ("doupi.icns" if sys.platform == "darwin" else "doupi.ico"))
data = [
    (str(root / "agent_nonsense" / "presets.json"), "agent_nonsense"),
    (str(root / "agent_nonsense" / "desktop" / "assets" / "agent-nonsense.ico"), "agent_nonsense/desktop/assets"),
    (str(root / "LICENSE"), "licenses"),
    (str(root / "packaging" / "THIRD_PARTY_NOTICES.md"), "licenses"),
    (str(root / "packaging" / "licenses"), "licenses"),
]
data += copy_metadata("PySide6-Essentials") + copy_metadata("shiboken6")
a = Analysis(
    [str(root / "packaging" / "entrypoint.py")], pathex=[str(root)],
    binaries=[], datas=data, hiddenimports=[],
    excludes=["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
options = dict(exclude_binaries=True, debug=False, strip=False, upx=False, icon=icon)
gui = EXE(pyz, a.scripts, [], name="Doupi", console=False, **options)
executables = [gui]
if sys.platform == "win32":
    # A console bootloader preserves the QProcess log pipes on Windows. It shares
    # the GUI's bundled runtime and modules, and is only launched as a child.
    server = EXE(pyz, a.scripts, [], name="doupi-server", console=True, **options)
    executables.append(server)
collection = COLLECT(*executables, a.binaries, a.datas, strip=False, upx=False, name="Doupi")
if sys.platform == "darwin":
    app = BUNDLE(
        collection, name="豆皮.app", icon=icon, bundle_identifier="io.github.wahahaha-cpu.doupi",
        info_plist={
            "CFBundleDisplayName": "豆皮", "CFBundleShortVersionString": version,
            "CFBundleVersion": version, "NSHighResolutionCapable": True,
            "NSPrincipalClass": "NSApplication",
            "LSMinimumSystemVersion": "13.0",
        },
    )
