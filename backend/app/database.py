from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url):
        if url.startswith('postgresql://'):
            url = 'postgresql+psycopg://' + url.removeprefix('postgresql://')
        if url.startswith('sqlite:///') and ':memory:' not in url:
            Path(url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
        self.sqlite = url.startswith('sqlite:')
        self.engine = create_engine(url, pool_pre_ping=True,
                                   connect_args={'check_same_thread': False, 'timeout': 30} if self.sqlite else {})
        if self.sqlite:
            @event.listens_for(self.engine, 'connect')
            def pragmas(connection, _):
                connection.execute('PRAGMA foreign_keys=ON')
                connection.execute('PRAGMA journal_mode=WAL')
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self):
        from . import models
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as conn:
            conn.execute(text('CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)'))
            row = conn.execute(text('SELECT version FROM schema_version')).first()
            if row is None:
                conn.execute(text('INSERT INTO schema_version (version) VALUES (2)'))
            elif row[0] == 1:
                column_type = 'BLOB' if self.sqlite else 'BYTEA'
                conn.execute(text(f'ALTER TABLE resumes ADD COLUMN content {column_type}'))
                conn.execute(text("UPDATE schema_version SET version = 2"))
            elif row[0] != 2:
                raise RuntimeError('Database schema version is unsupported')

    @contextmanager
    def transaction(self):
        with self.sessions() as session:
            try:
                if self.sqlite:
                    session.execute(text('BEGIN IMMEDIATE'))
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise
