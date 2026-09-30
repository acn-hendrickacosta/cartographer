# Python: Testing

- Use pytest. Name test files `test_*.py`, test functions `test_*`, and test classes `Test*`. Configure `testpaths`, `python_files`, and markers in `pyproject.toml` under `[tool.pytest.ini_options]`.
- Each test function should test one behavior. The test name should read as a sentence describing what is expected: `test_user_login_fails_with_wrong_password`, not `test_login2`.
- Tests must be independent and runnable in any order. Do not share mutable state between tests. Use fixtures for setup; do not rely on ordering or test class state.
- Use `@pytest.fixture` for test setup. Prefer fixtures over class-level `setUp`/`tearDown`. Use `yield` in a fixture for setup+teardown in one function.
- Control fixture scope explicitly. Use the default `function` scope for most fixtures. Use `module` or `session` scope only for resources that are expensive to create and safe to share (e.g., a read-only parsed document, a database connection pool).
- Put fixtures shared across multiple test files in `conftest.py`. Pytest discovers `conftest.py` automatically; no imports are needed.
- Use `@pytest.mark.parametrize` to run the same test with multiple inputs. Give each case a readable `id` when the parameters are not self-explanatory:

```python
@pytest.mark.parametrize("email,valid", [
    ("user@example.com", True),
    ("not-an-email", False),
], ids=["valid", "missing-at"])
def test_email_validation(email, valid):
    assert is_valid_email(email) == valid
```

- Declare custom markers in `pyproject.toml` and use `--strict-markers` to fail fast when an undeclared marker is used. Common markers: `slow`, `integration`, `unit`.
- Use `pytest.raises(ExceptionType, match="regex")` to assert both the exception type and message. Check `exc_info.value` attributes when the exception carries structured data.
- Use `tmp_path` (a `pathlib.Path` to a per-test temp directory) for filesystem tests. Pytest cleans it up automatically. Prefer it over `tempfile.mkdtemp()`.
- Mock external dependencies with `unittest.mock.patch`. Patch the name as it is imported in the module under test, not where it is defined. Use `autospec=True` to catch calls that do not match the real object's signature.
- Mock async functions with `AsyncMock`. Check that async mocks were awaited with `assert_awaited_once()`.
- For async tests, use `pytest-asyncio` and mark tests with `@pytest.mark.asyncio`. Configure `asyncio_mode = "auto"` in `pyproject.toml` to avoid repeating the marker on every async test.
- Prefer real objects and `tmp_path` over mocking the filesystem or a database when the real thing is cheap to construct. Over-mocking produces tests that pass even when the real code is broken.
- Do not test third-party library behavior. Test your own code's interaction with the library. Trust that the library works; verify your usage of it.
- Run the full test suite with coverage in CI: `pytest --cov=src --cov-report=term-missing --cov-fail-under=80`.
