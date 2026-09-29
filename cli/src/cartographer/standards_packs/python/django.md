# Django

## Project structure and settings

- Split settings into `base.py`, `development.py`, `production.py`, and `test.py`. Base holds shared configuration; environment-specific files import from base and override. Set `DJANGO_SETTINGS_MODULE` in the environment, not in code.
- Define a custom user model (`AbstractUser` subclass) at project start. Set `AUTH_USER_MODEL` in `settings/base.py` before the first migration. Adding a custom user model after migrations have run is painful and error-prone.
- Organize apps under an `apps/` directory. Each app should have its own `models.py`, `views.py`, `serializers.py`, `services.py`, `urls.py`, and `tests/` directory.

## ORM patterns

- Use custom `QuerySet` classes for reusable query methods (`active()`, `in_stock()`, `with_category()`). Attach them via `objects = MyQuerySet.as_manager()`. This keeps filtering logic close to the model and prevents duplication in views.
- Always use `select_related()` for ForeignKey/OneToOne traversals in loops, and `prefetch_related()` for ManyToMany. Accessing a related object inside a loop without prefetching generates N+1 queries.
- Use `.count()` not `len(queryset)`. Use `.exists()` not `if queryset:` or `if queryset.count() > 0`. These evaluate the queryset without fetching objects.
- Use `transaction.atomic()` for any sequence of two or more database writes. A partial failure in a multi-step write that is not wrapped in a transaction leaves the database inconsistent.
- Use `bulk_create`, `bulk_update`, and `.update()` for set operations. Never loop calling `.save()` on individual instances when you can express the change as a set operation.
- When calling `.save()` to update a subset of fields, use `update_fields=['field_name']` to avoid overwriting concurrent writes to other columns.
- Define database `indexes` and `constraints` in `Meta`. Do not rely on application-level checks for uniqueness — they are race-prone. Add database-level unique constraints for correctness.

## Django REST Framework

- Always declare explicit `fields` on serializers. Never use `fields = '__all__'` — it exposes all columns including sensitive ones and any added in future migrations.
- Mark auto-generated fields (`id`, `created_at`, `updated_at`) as `read_only_fields`. They should not be writable via the API.
- Add pagination to all list endpoints. An unbounded query on a large table is a denial-of-service vector.
- Declare `permission_classes` explicitly on every view or viewset. Do not rely solely on global defaults — defaults are easy to misconfigure as the project grows.
- Inject request context (current user, organization, etc.) in `perform_create` / `perform_update`, not in `validate()`. The serializer's validation methods should not access `self.context["request"]` for mutation logic.
- Apply DRF throttling to auth endpoints (login, registration, password reset). Configure burst and sustained rate limits separately.

## Service layer

- Keep business logic out of views and serializers. Create a `services.py` per app for complex operations. Views call services; serializers validate data shapes; models own the data.
- Use `@transaction.atomic` on service methods that perform multiple writes. The atomic decorator ensures the full operation succeeds or rolls back cleanly.

## Migrations

- Every model change must have a corresponding migration. Run `python manage.py makemigrations --check` in CI to detect missing migrations before they reach production.
- Never edit a migration that has already run in any environment. Create a new forward migration instead.
- Remove all application references to a column before dropping it. The removal and the `DROP COLUMN` migration must be in separate deployments; otherwise the application breaks before the migration runs.
- `RunPython` operations must include a `reverse_code` function or be explicitly marked irreversible. Migrations without a reverse block all rollbacks.
- Never use `atomic = False` on a migration without documenting why. Leaving the database in a partial state on failure is rarely acceptable.

## Security

- Production settings must have `DEBUG = False`. Never deploy with `DEBUG = True` — it leaks stack traces, internal settings, and SQL queries to the browser.
- Load `SECRET_KEY` from an environment variable. Raise `ImproperlyConfigured` if it is absent. Never commit a secret key to version control.
- Enable all security headers in production: `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS = "DENY"`.
- Never call `mark_safe()` on user input without `escape()` first. Django auto-escapes template variables, but `mark_safe` bypasses that protection.
- Never concatenate user input into raw SQL. If you must use `raw()`, always use `%s` parameters: `User.objects.raw("SELECT * FROM users WHERE email = %s", [email])`.
- Use `@csrf_exempt` only on webhook endpoints that receive signed payloads from external services. Add a comment explaining why and how the authenticity is verified.
- Validate file uploads: check the MIME type from the file's magic bytes (not just the extension) and enforce a maximum size. Serve uploads from a separate origin or object store.

## Signals and app configuration

- Register signal receivers in `AppConfig.ready()`. Signals connected at module import time may run before the app is fully configured.
- Prefer explicit service calls over signals for critical business flows. Signals are hard to trace, test, and debug. Use them for genuinely decoupled, optional side effects (e.g., sending a notification after a model save).
- Every model must define `__str__`. The Django admin and log output are uninformative without it.
