"""Initialize or migrate the ApplyWell database to the current schema."""
from .app.config import Settings
from .app.database import Database


def main():
    db = Database(Settings.from_env().database_url)
    db.initialize()
    db.engine.dispose()
    print('Database schema version 2 is ready.')


if __name__ == '__main__':
    main()
