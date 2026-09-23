# Python standards

- Target the Python version declared in `pyproject.toml`. Use type hints on public
  function signatures; let local variables infer where the type is obvious.
- Prefer standard library and already-installed dependencies over adding a new one.
  Justify a new dependency by what it saves, not by convenience alone.
- Structure packages with a `src/` layout and an explicit `pyproject.toml`. Avoid
  `sys.path` manipulation to make imports work.
- Use `pytest` for tests. Name test files `test_*.py` and keep one behavior under
  test per test function. Prefer real objects and `tmp_path` over mocking the
  filesystem or a database when the real thing is cheap to construct.
- Raise specific exceptions with a message that states what was expected and what
  was found. Do not catch broad exceptions except at a boundary where you must
  convert failures into a user-facing report (a CLI command, a hook).
- Format with the project's configured formatter and let it own style disputes.
