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
- Use `black` for formatting, `isort` or `ruff` for import ordering, and `ruff` for linting. Do not configure competing tools that override each other.
- Prefer immutable data structures. Use `@dataclass(frozen=True)` for value objects; use `typing.NamedTuple` for simple immutable records. Mutability should be intentional, not the default.
- Use `logging.getLogger(__name__)` instead of `print()`. Log at the appropriate level (`debug`, `info`, `warning`, `error`); never use print for operational output in library or server code.
- Write docstrings on all public functions, classes, and modules. Explain the purpose and any non-obvious behavior; parameter names and types are already expressed in the signature.
- Do not shadow built-in names (`list`, `dict`, `str`, `id`, `type`, `input`, `open`). Shadowing makes code confusing and breaks tooling that depends on the built-in.
- Use `pytest.mark` to categorize tests. Declare markers in `pyproject.toml` under `[tool.pytest.ini_options] markers`. At minimum, distinguish `unit` and `integration` tests so slow or database-dependent tests can be skipped in fast feedback loops.
- Tag slow tests with `@pytest.mark.slow` and use `pytest -m "not slow"` for pre-commit or interactive runs.
- Target 80%+ code coverage overall; aim for 100% on critical paths (auth, billing, data-loss-risk code). Measure with `pytest --cov=src --cov-report=term-missing`.
