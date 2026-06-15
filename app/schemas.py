import re

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    """
    Registration payload.

    Usernames are forced to lowercase before validation to prevent
    impersonation via case variants (e.g. 'Admin' vs 'admin').
    """

    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) < 3 or len(v) > 32:
            raise ValueError("Username must be 3-32 characters")
        if not re.match(r"^[a-z0-9_]+$", v):
            raise ValueError(
                "Username may only contain lowercase letters, digits, and underscores"
            )
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLogin(BaseModel):
    """Login payload. Username is normalised to lowercase."""

    username: str
    password: str

    @field_validator("username")
    @classmethod
    def normalise_username(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    """Token pair returned on successful login or refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Payload for the /refresh endpoint."""

    refresh_token: str


class UserResponse(BaseModel):
    """
    Public user representation — never includes password_hash.

    ``from_attributes`` allows direct construction from a SQLAlchemy
    User instance (e.g. ``UserResponse.model_validate(user_obj)``).
    """

    id: int
    username: str
    email: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class PaginatedMemories(BaseModel):
    """
    Cursor-based pagination wrapper for memory listing and export.

    ``next_cursor`` is the Qdrant point ID to pass as ``cursor`` on
    the next request. When ``None``, there are no more pages.
    """

    memories: list[dict]
    next_cursor: str | None = None
    count: int = Field(description="Number of memories in this page")
