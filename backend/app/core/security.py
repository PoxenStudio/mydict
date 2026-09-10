import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt

from app.core.config import get_settings

ACCESS_TOKEN_TTL = timedelta(hours=2)
REFRESH_TOKEN_TTL = timedelta(days=30)

AUD_ADMIN = "admin"
AUD_USER = "user"


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode(), hashed.encode())


def hash_api_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_api_token() -> str:
    return "sk-" + secrets.token_urlsafe(32)


def token_display_prefix(raw: str) -> str:
    return raw[:9] + "****"


def generate_temp_password() -> str:
    return secrets.token_urlsafe(9)


def _load_or_create_jwt_secret() -> str:
    settings = get_settings()
    if settings.jwt_secret:
        return settings.jwt_secret

    key_path = Path(settings.config_storage_path) / "jwt_secret.key"
    if key_path.exists():
        return key_path.read_text().strip()

    key_path.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_urlsafe(48)
    key_path.write_text(secret)
    return secret


def _create_token(subject: int, aud: str, scope: str, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "aud": aud,
        "scope": scope,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, _load_or_create_jwt_secret(), algorithm="HS256")


def create_access_token(subject: int, aud: str) -> str:
    return _create_token(subject, aud, "access", ACCESS_TOKEN_TTL)


def create_refresh_token(subject: int, aud: str) -> str:
    return _create_token(subject, aud, "refresh", REFRESH_TOKEN_TTL)


def decode_token(token: str, aud: str) -> dict:
    return jwt.decode(token, _load_or_create_jwt_secret(), algorithms=["HS256"], audience=aud)
