# auth.py
import hmac
import secrets
import string

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def generate_token() -> str:
    """Return a 32-byte (64 hex char) cryptographically random session token."""
    return secrets.token_hex(32)


def generate_invite_code() -> str:
    """Return a random 8-character uppercase alphanumeric invite code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def compare_codes(a: str, b: str) -> bool:
    """Constant-time string comparison — prevents timing attacks on invite codes."""
    return hmac.compare_digest(a, b)
