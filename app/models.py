from datetime import datetime, UTC

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey

from app.database import Base


class User(Base):
    """
    Represents a registered Memoria user.

    Passwords are never stored in plaintext — only bcrypt hashes.
    Usernames are stored lowercase and must be unique.
    Emails are stored lowercase and must be unique.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(32), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


class RefreshToken(Base):
    """
    Stores hashed refresh tokens for stateful token rotation.

    Security design:
    - Tokens are stored as SHA-256 hashes — a database breach does not
      directly expose bearer tokens.
    - ``is_revoked`` enables instant invalidation on logout or rotation.
    - ``expires_at`` enforces a hard TTL even if revocation is missed.
    - Indexed on ``token_hash`` for O(1) lookup during /refresh calls.
    - Indexed on ``user_id`` for efficient revocation of all user sessions.
    """

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    is_revoked = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, revoked={self.is_revoked})>"
