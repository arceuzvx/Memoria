import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./memoria.db")

engine = create_engine(
    DATABASE_URL,
    # SQLite does not allow multiple threads to share a single connection
    # by default. FastAPI handles requests in a threadpool, so we must
    # disable this check to avoid "SQLite objects created in a thread can
    # only be used in that same thread" errors.
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    FastAPI dependency — yields a scoped SQLAlchemy session.

    Usage:
        @app.get("/example")
        def example(db: Session = Depends(get_db)):
            ...

    The session is automatically closed after the request completes,
    even if the handler raises an exception.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
