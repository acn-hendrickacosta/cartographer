# Django: Testing

- Use `pytest-django`. Point `DJANGO_SETTINGS_MODULE` at a dedicated test settings module in `pytest.ini` or `pyproject.toml`. Do not run tests against development or production settings.
- Test settings should use an in-memory SQLite database, a fast password hasher (`MD5PasswordHasher` for tests), and `CELERY_TASK_ALWAYS_EAGER = True` if Celery is used.
- Disable migrations in test settings for speed. Use a `DisableMigrations` class that returns `None` for every app, or use the `--nomigrations` flag via `pytest-django`. Run the real migration suite in a separate CI job.
- Mark tests that need database access with `@pytest.mark.django_db`. Tests without this marker run without a database and will raise if they try to make queries — a useful protection against accidental DB access in unit tests.
- Use `factory_boy` (`factory.django.DjangoModelFactory`) to create test objects instead of `Model.objects.create()`. Factories document the minimal required data, generate realistic values with `factory.Faker`, and make it easy to create variations with keyword overrides.
- Use `factory.create_batch(n)` to create multiple objects. Use `factory.build()` (no DB write) for testing object construction and validation logic.
- Test permissions explicitly. For every protected endpoint, write a test that verifies an unauthenticated request returns 401 and an unauthorized request returns 403. These regressions are silent without coverage.
- Use `api_client.force_authenticate(user=user)` for testing business logic that requires authentication. Write separate tests that exercise the actual authentication flow without force-authenticate.
- Use `client.force_login(user)` for Django view tests. Do not test session internals; test the HTTP response.
- Use `@override_settings(...)` to temporarily change a setting for one test or test class. Restore state after the test — the decorator handles this automatically.
- Inspect sent emails via `django.core.mail.outbox` (available when `EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'`). Check recipient, subject, and body.
- Mock external service calls (payment gateways, third-party APIs, email providers) with `unittest.mock.patch`. Tests must not make real network requests.
- Use `--reuse-db` in development to speed up repeated test runs. Use `--create-db` in CI to ensure a clean baseline.
- Coverage targets by component: models 90%+, services 90%+, serializers 85%+, views 80%+. Measure with `pytest --cov=apps --cov-report=term-missing`.
