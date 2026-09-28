# Python: Dependencies and packaging

- Declare all direct dependencies in `pyproject.toml` under `[project] dependencies`. Do not use `requirements.txt` as the source of truth for installed packages; it is a secondary lock file, not the spec.
- Pin dependencies to a minimum version (`>=x.y`) in `pyproject.toml` and let the lock file pin exact versions for reproducible installs. Do not pin exact versions in `pyproject.toml` unless a hard upper bound is known to be necessary.
- Keep optional extras (e.g., `[embed]`, `[ui]`) separate from required dependencies. A user who does not need a feature should not be required to install its dependencies.
- Before adding a dependency, confirm it is not already provided by an existing install or the standard library. One justified dependency beats three small ones that each do part of the same job.
- Do not import optional dependencies at the module level. Guard with a try/except ImportError or a lazy import inside the function that needs it, and raise a clear error with an install hint.
- Keep the virtual environment out of version control. `.venv/` and `venv/` belong in `.gitignore`. Record the Python version requirement in `pyproject.toml [project] requires-python`, not in a separate `.python-version` file unless the toolchain demands it.
