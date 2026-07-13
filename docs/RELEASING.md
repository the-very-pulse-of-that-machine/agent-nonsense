# Releasing Agent Nonsense

1. Update the version in `pyproject.toml`, `agent_nonsense/__init__.py`, and `MockAgentServer.server_version`.
2. Move pending changes into a dated section in `CHANGELOG.md`.
3. Run:

   ```powershell
   python -m unittest discover -s tests -v
   python -m compileall -q agent_nonsense
   python -m pip wheel --no-deps --no-build-isolation . -w dist
   ```

4. Install the wheel into a fresh virtual environment and run `agent-nonsense --help` plus a finite Responses API smoke test.
5. Inspect the wheel to confirm that `agent_nonsense/presets.json`, `LICENSE`, and metadata are present.
6. Tag the release as `vX.Y.Z` and create a GitHub release from the changelog notes.
7. Publish to PyPI only after confirming the distribution name and ownership.

Do not publish from an unclean working tree or skip the sandbox and continuous-disconnect tests.
