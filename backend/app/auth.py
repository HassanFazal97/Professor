import os
from datetime import UTC, datetime, timedelta

import httpx
from jose import JWTError, jwt
from passlib.context import CryptContext

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Verify and return user_id (sub claim). Raises ValueError on failure."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        sub = payload.get("sub")
        if not sub:
            raise ValueError("Missing sub claim")
        return str(sub)
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e


async def verify_google_token(id_token: str) -> dict:
    """Call Google's tokeninfo endpoint to validate an id_token.
    Returns dict with sub, email, name, picture.
    """
    if not GOOGLE_CLIENT_ID:
        raise ValueError("GOOGLE_CLIENT_ID not configured")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
            timeout=10.0,
        )
    if resp.status_code != 200:
        raise ValueError("Google token verification failed")
    data = resp.json()
    if data.get("aud") != GOOGLE_CLIENT_ID:
        raise ValueError("Token audience mismatch")
    return {
        "sub": data["sub"],
        "email": data["email"],
        "name": data.get("name", ""),
        "picture": data.get("picture", ""),
    }
