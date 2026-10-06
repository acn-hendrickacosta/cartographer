"""Configuration, read from environment variables.

Mirrors the CLI's config.py convention of env-var-driven settings for
anything that varies between local dev and the real EKS deployment --
no separate config file format introduced for this service.
"""

from __future__ import annotations

import os


class Settings:
    aws_region: str = os.environ.get("AWS_REGION", "us-east-1")

    cognito_pool_id: str = os.environ["COGNITO_POOL_ID"]
    cognito_client_id: str = os.environ["COGNITO_CLIENT_ID"]
    cognito_client_secret: str = os.environ["COGNITO_CLIENT_SECRET"]
    cognito_domain: str = os.environ["COGNITO_DOMAIN"]  # e.g. cartographer-standards-11439652

    registry_bucket: str = os.environ["REGISTRY_BUCKET"]

    # App state (registry tokens now, SR.3's draft/review tables later) lives
    # in Postgres -- the same technology (and, for local dev, the literal
    # same container: cli/tests/docker-compose.yml's pgvector service) the
    # CLI's own central VDB backend already uses, so this app doesn't add a
    # second stateful service (DynamoDB) alongside it. A separate database
    # within that instance/container (not the CLI test suite's own database)
    # keeps the two concerns from colliding. In production this points at a
    # real RDS/Aurora Postgres instance instead of the local Docker container.
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql://cartographer:cartographer@localhost:5433/cartographer_webapp"
    )

    session_secret: str = os.environ.get("SESSION_SECRET", "dev-only-insecure-secret-change-me")

    base_url: str = os.environ.get("BASE_URL", "http://localhost:8000")

    @property
    def cognito_issuer(self) -> str:
        return f"https://cognito-idp.{self.aws_region}.amazonaws.com/{self.cognito_pool_id}"

    @property
    def cognito_jwks_url(self) -> str:
        return f"{self.cognito_issuer}/.well-known/jwks.json"

    @property
    def cognito_hosted_ui_base(self) -> str:
        return f"https://{self.cognito_domain}.auth.{self.aws_region}.amazoncognito.com"

    @property
    def redirect_uri(self) -> str:
        return f"{self.base_url}/auth/callback"


settings = Settings()
