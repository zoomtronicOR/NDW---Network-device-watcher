from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# client_encoding pinned explicitly: the database was originally created as
# SQL_ASCII (cluster initialized under LANG=C), which made psycopg2 reject any
# Serbian diacritics (š, đ, č, ć, ž). The DB is now UTF8; this keeps the
# connection UTF-8 regardless of server/cluster defaults.
engine = create_engine(settings.database_url, pool_pre_ping=True, client_encoding="utf8")
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
