"""
Passwords and sign-in tokens.

Passwords are never stored: only a salted PBKDF2 hash (built into Python).

After sign in, the user gets two signed tokens (JSON Web Tokens, made with the PyJWT package):
    access token    valid 15 minutes   checked on every page
    refresh token   valid 7 days       when the access token has expired, it gives a new one (no new sign in)
Nothing is saved in the database for a token. A token carries the user's id, its type ("access" / "refresh")
and the user's token_version. It is signed with JWT_SECRET (.env), so nobody can make or change one.
Log out adds 1 to the user's token_version: every token made before stops working.
"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from config.settings import JWT_SECRET

ITERATIONS = 200_000
ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 7
ALGORITHM = "HS256"


# ---------------------------------------------------------------- passwords

def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------- tokens

def create_token(user, token_type):
    """A new signed token for this user. token_type is "access" (15 minutes) or "refresh" (7 days)."""
    now = datetime.now(timezone.utc)
    if token_type == "access":
        expires = now + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    else:
        expires = now + timedelta(days=REFRESH_TOKEN_DAYS)
    payload = {
        "sub": str(user["id"]),          # who the token belongs to
        "type": token_type,              # "access" or "refresh"
        "ver": user["token_version"],    # stops working when the user logs out (the version goes up)
        "iat": now,                      # made at
        "exp": expires,                  # expires at
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def read_token(token, token_type):
    """
    The data inside the token, e.g. {"sub": "1", "type": "access", "ver": 0, ...},
    or None if the token is missing, fake, changed, expired, or of the other type.
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:        # wrong signature, expired, damaged...
        return None
    if payload.get("type") != token_type:
        return None
    return payload
