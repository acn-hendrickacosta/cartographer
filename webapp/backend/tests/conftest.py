"""Sets required env vars before any `app.*` module is imported -- settings.py
reads several as required (no default), matching config.py's CLI-side
convention of failing fast on missing required config rather than silently
defaulting. Real values are only needed for the handful of tests that hit
real AWS; everything else here uses these placeholders with mocked clients.
"""

import os

os.environ.setdefault("COGNITO_POOL_ID", "us-east-1_test")
os.environ.setdefault("COGNITO_CLIENT_ID", "test-client-id")
os.environ.setdefault("COGNITO_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("COGNITO_DOMAIN", "test-domain")
os.environ.setdefault("REGISTRY_BUCKET", "test-bucket")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
