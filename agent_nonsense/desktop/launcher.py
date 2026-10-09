"""Entry point shared by the frozen GUI and its owned server process."""
import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    if sys.argv[1:2] == ["--doupi-server"]:
        sys.argv.pop(1)
        for stream in (sys.stdout, sys.stderr):
            if stream is not None and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", line_buffering=True)
        from agent_nonsense.server import main as server_main
        return server_main()
    if sys.argv[1:2] == ["--self-test"]:
        if len(sys.argv) != 3:
            raise SystemExit("Usage: Doupi --self-test REPORT.json")
        from .selftest import run
        raise SystemExit(run(sys.argv[2]))
    from . import main as desktop_main
    return desktop_main()
