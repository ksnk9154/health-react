import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv


# Load environment variables from backend/.env BEFORE reading any config below.
# This is required because this module can be imported (via api/routes/auth.py)
# before db/session.py triggers load_dotenv(), which would otherwise leave
# JWT_SECRET unset and fall back to the insecure default.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))


JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALG = os.environ.get("JWT_ALG", "HS256")
ACCESS_TOKEN_TTL_MIN = int(os.environ.get("ACCESS_TOKEN_TTL_MIN", "15"))
REFRESH_TOKEN_TTL_DAYS = int(os.environ.get("REFRESH_TOKEN_TTL_DAYS", "30"))


def _validate_secret() -> None:
    """Refuse to sign tokens with a missing or weak (< 32 bytes) secret."""
    if not JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET is not set. Add a strong random value to backend/.env "
            "as: JWT_SECRET=<random> via "
            "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
    if len(JWT_SECRET.encode("utf-8")) < 32:
        raise RuntimeError(
            "JWT_SECRET is too short (must be at least 32 bytes). "
            "Generate a strong value with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )



def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(*, user_id: int) -> str:
    _validate_secret()
    now = _utcnow()
    exp_dt = now + timedelta(minutes=ACCESS_TOKEN_TTL_MIN)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(exp_dt.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)




def create_refresh_token(*, user_id: int) -> str:
    _validate_secret()
    now = _utcnow()
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token")
    return payload




def decode_refresh_token(token: str) -> dict:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("Not a refresh token")
    return payload

