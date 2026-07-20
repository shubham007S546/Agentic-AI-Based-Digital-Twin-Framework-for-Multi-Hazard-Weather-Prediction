"""
app/security/authentication/passwords.py
────────────────────────────────────────
Password hashing utilities using passlib.

Design decisions:
  • Uses bcrypt (default enterprise standard) with a high work factor.
  • Passwords are NEVER logged, and hashes are only kept in memory as long as needed.
  • `pwd_context.verify` is resistant to timing attacks.
"""

from passlib.context import CryptContext

# Create a single CryptContext using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.
    Safe against timing attacks.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Generate a bcrypt hash for a plaintext password.
    """
    return pwd_context.hash(password)
