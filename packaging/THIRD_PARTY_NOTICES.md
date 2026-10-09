# Third-party software

Doupi bundles Python, PySide6 Essentials / Shiboken6, Qt and the PyInstaller
bootloader. Original Doupi source is distributed under the included MIT license.

- Python: https://docs.python.org/3/license.html (PSF license and notices).
- PySide6 / Shiboken6: https://doc.qt.io/qtforpython-6/licenses.html
  (LGPLv3 / GPLv3 / commercial licensing; this distribution uses open-source terms).
- Qt: https://www.qt.io/licensing/open-source-lgpl-obligations
  and https://code.qt.io/ (corresponding upstream source).
- PyInstaller: https://pyinstaller.org/en/stable/license.html
  (GPLv2 with the exception permitting distribution of bundled applications).

Full LGPLv3, GPLv3, Qt GPL exception, Python license and PyInstaller exception
texts are included in this directory. PySide6 and Shiboken6 distribution metadata
are retained in the bundle. Qt is dynamically linked in the onedir/app bundle;
users may replace the libraries with compatible modified versions. Do not move
the executable away from its companion runtime. Exact dependency versions are
recorded in BUILD-INFO.json next to each downloadable installer.
