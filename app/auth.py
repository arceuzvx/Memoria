"""
Authentication module for Memoria.

Handles user registration, login, JWT issuance, refresh-token rotation,
logout, and request-level authentication via the ``get_current_user``
dependency.

Security notes
--------------
- Passwords are hashed with bcrypt via passlib (constant-time verify).
- JWT access tokens carry minimal claims (``sub`` + ``exp``) — no PII.
- Refresh tokens are cryptographically random (32 bytes, URL-safe) and
  stored as SHA-256 hashes — a database breach does not expose raw tokens.
- Token rotation: on each /refresh call the old token is revoked and a
  new pair (access + refresh) is issued. This limits the window for
  replay attacks.
- Login and registration return generic error messages to prevent
  user-enumeration attacks.
- Rate limiting is applied to /register, /login, /refresh, and /logout
  to mitigate brute-force and credential-stuffing attacks.
"""

import hashlib
import os
import logging
import secrets
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, RefreshToken
from app.schemas import (
    UserRegister,
    UserLogin,
    TokenResponse,
    RefreshRequest,
    UserResponse,
)


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
# Key function resolves the client's real IP.  In production behind a
# reverse proxy, configure trusted proxy headers (X-Forwarded-For) or
# swap ``get_remote_address`` for a proxy-aware resolver.

limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
# ``deprecated="auto"`` lets passlib transparently re-hash passwords
# if we ever migrate away from bcrypt — a single-line config change.

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password*."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify *plain_password* against a bcrypt *hashed_password*.

    Uses constant-time comparison internally to prevent timing attacks.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(user_id: int) -> str:
    """
    Create a signed JWT with the user's ID as the ``sub`` claim.

    The token expires after ``JWT_EXPIRE_MINUTES`` (default 30).
    """
    expire = datetime.now(UTC) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Refresh token helpers
# ---------------------------------------------------------------------------

def _hash_token(raw_token: str) -> str:
    """SHA-256 hash a raw refresh token for database storage."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_refresh_token(user_id: int, db: Session) -> str:
    """
    Generate a cryptographically random refresh token, store its
    SHA-256 hash in the database, and return the raw token.

    The caller must send the raw token to the client; only the hash
    is persisted.
    """
    raw_token = secrets.token_urlsafe(32)

    db_token = RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(db_token)
    db.commit()

    return raw_token


def validate_refresh_token(raw_token: str, db: Session) -> RefreshToken:
    """
    Validate a raw refresh token against the database.

    Returns the ``RefreshToken`` row if valid.  Raises ``401`` if the
    token is unknown, revoked, or expired.
    """
    token_hash = _hash_token(raw_token)

    db_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .first()
    )

    if db_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if db_token.is_revoked:
        # Possible token replay attack — revoke ALL tokens for this user
        # as a precaution (the attacker may hold other tokens too).
        db.query(RefreshToken).filter(
            RefreshToken.user_id == db_token.user_id
        ).update({"is_revoked": True})
        db.commit()
        logger.warning(
            "Refresh token replay detected for user_id=%d — all sessions revoked",
            db_token.user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    if db_token.expires_at < datetime.now(UTC).replace(tzinfo=None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    return db_token


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency — authenticates the current request.

    Extracts the Bearer token from the ``Authorization`` header,
    decodes and validates the JWT, then loads the corresponding user
    from the database.

    Raises ``401 Unauthorized`` if:
    - the token is missing, malformed, or expired
    - the ``sub`` claim is absent
    - no user exists for the embedded user ID

    Usage:
        @app.get("/protected")
        def protected(user: User = Depends(get_current_user)):
            ...
    """
    token = credentials.credentials

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM]
        )
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id_str)).first()
    if user is None:
        raise credentials_exception

    return user


# ---------------------------------------------------------------------------
# Router — /register, /login, /refresh, /logout
# ---------------------------------------------------------------------------

router = APIRouter(tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account",
)
@limiter.limit("3/minute")
def register(
    request: Request,
    data: UserRegister,
    db: Session = Depends(get_db),
):
    """
    Register a new Memoria user.

    - Validates username (lowercase, 3-32 chars, alphanumeric + underscores)
    - Validates email format
    - Enforces minimum 8-character password
    - Hashes the password with bcrypt before storage
    - Returns 409 if username or email is already taken
    """
    existing = (
        db.query(User)
        .filter((User.username == data.username) | (User.email == data.email.lower()))
        .first()
    )

    if existing:
        # Generic message to prevent user-enumeration — do not reveal
        # whether it was the username or the email that conflicted.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account already exists",
        )

    user = User(
        username=data.username,  # already lowercase from validator
        email=data.email.lower(),
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("User registered: %s (id=%d)", user.username, user.id)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive a token pair",
)
@limiter.limit("5/minute")
def login(
    request: Request,
    data: UserLogin,
    db: Session = Depends(get_db),
):
    """
    Authenticate with username + password.

    Returns a short-lived JWT access token and a long-lived refresh
    token.  Use the refresh token at ``POST /refresh`` to obtain a
    new pair without re-entering credentials.
    """
    user = db.query(User).filter(User.username == data.username).first()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id, db)

    logger.info("User logged in: %s (id=%d)", user.username, user.id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate tokens using a refresh token",
)
@limiter.limit("10/minute")
def refresh(
    request: Request,
    data: RefreshRequest,
    db: Session = Depends(get_db),
):
    """
    Exchange a valid refresh token for a new access + refresh token pair.

    The old refresh token is revoked immediately (token rotation).
    If a revoked token is reused, ALL of that user's sessions are
    invalidated as a security precaution — this indicates a possible
    token-theft replay attack.
    """
    db_token = validate_refresh_token(data.refresh_token, db)

    # Revoke the old token (rotation)
    db_token.is_revoked = True
    db.commit()

    # Issue new pair
    access_token = create_access_token(db_token.user_id)
    new_refresh_token = create_refresh_token(db_token.user_id, db)

    logger.info("Token rotated for user_id=%d", db_token.user_id)
    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current refresh token",
)
@limiter.limit("10/minute")
def logout(
    request: Request,
    data: RefreshRequest,
    db: Session = Depends(get_db),
):
    """
    Revoke a refresh token, ending the session.

    The access token remains valid until it expires (stateless JWTs
    cannot be revoked without a blocklist). For immediate access-token
    invalidation, implement a token blocklist in a future phase.
    """
    token_hash = _hash_token(data.refresh_token)

    db_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .first()
    )

    if db_token and not db_token.is_revoked:
        db_token.is_revoked = True
        db.commit()
        logger.info("User logged out (token revoked), user_id=%d", db_token.user_id)

    # Always return 204 — don't reveal whether the token was valid.
    # This prevents an attacker from probing token validity.
    return None
