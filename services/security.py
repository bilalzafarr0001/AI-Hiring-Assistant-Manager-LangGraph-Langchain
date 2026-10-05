"""Safe password storage and login tokens (built into Python, no extra package needed)."""
import hashlib
import hmac
import os
import secrets

ITERATIONS = 200_000
TOKEN_DAYS = 7   # how long a login stays valid


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


def new_token():
    """A new random login token (43 letters, digits, - and _). Nobody can guess it."""
    return secrets.token_urlsafe(32)


def hash_token(token):
    """
    The database keeps only this hash of the token, never the token itself.
    So even someone with a copy of the database cannot use it to log in.
    """
    return hashlib.sha256(token.encode()).hexdigest()
