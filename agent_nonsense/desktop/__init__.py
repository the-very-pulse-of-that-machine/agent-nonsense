"""Optional Qt desktop application. The API server stays dependency-free."""


def main():
    import sys

    try:
        from .window import run
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("PySide6"):
            message = '豆皮 GUI 需要 Qt。请先运行：python -m pip install ".[gui]"'
            print(message, file=sys.stderr)
            # Windows gui-scripts have no console; show an actionable error there.
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, message, "豆皮 · 缺少界面依赖", 0x10)
            raise SystemExit(1) from exc
        raise
    raise SystemExit(run())
