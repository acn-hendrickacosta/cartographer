# Python: Security

- Never build SQL queries with f-strings, `%` formatting, or string concatenation on user input. Always use parameterized queries (`cursor.execute("SELECT * FROM users WHERE id = %s", [user_id])`) or the ORM. A raw query must never interpolate user-controlled values directly.
- Never pass user-controlled strings to `subprocess.run(shell=True)`, `os.system()`, `eval()`, or `exec()`. Use `subprocess.run` with a list of arguments (`subprocess.run(["ls", path], ...)`) so the shell is never invoked.
- Validate and normalize user-controlled file paths before any read or write. Use `Path(user_input).resolve()` and assert the resolved path starts with the expected root. Reject any path that contains `..` or points outside the allowed directory.
- Never hardcode secrets (API keys, passwords, tokens, private keys) in source code. Read them from environment variables with `os.environ["SECRET_KEY"]` (which raises `KeyError` if missing, failing loudly at startup). Do not use `os.environ.get("KEY")` for required secrets — silent `None` is a misconfiguration bug.
- Use `yaml.safe_load()` not `yaml.load()`. The unsafe loader can construct arbitrary Python objects from attacker-controlled YAML.
- Do not use MD5 or SHA-1 for security-critical operations — password hashing, HMAC for tokens, or file integrity checks that inform trust decisions. Use `hashlib.sha256` or higher for digests. Use `argon2-cffi`, `passlib[bcrypt]`, or similar for password hashing.
- Do not use `pickle` or `marshal` to deserialize data from an untrusted source. These formats execute arbitrary code during deserialization. Use JSON, msgpack, or a schema-validated format.
- Validate file uploads by reading magic bytes to determine actual MIME type, not just the extension. Enforce a maximum file size before writing to disk. Serve user-uploaded files from a separate origin or object store, never from the same domain as the application.
- Run `bandit -r src/` in CI to catch common security anti-patterns automatically. Treat bandit medium/high findings as blocking.
- Redact secrets, authorization headers, cookies, and tokens from log output. Never log a full request or response body that might contain credentials.
