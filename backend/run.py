"""Start the local API and worker together: python -m backend.run."""
import argparse
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default=os.getenv('HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '8000')))
    args = parser.parse_args()
    from .app.config import Settings
    from .app.database import Database
    settings = Settings.from_env()
    db = Database(settings.database_url)
    db.initialize()
    db.engine.dispose()
    process = subprocess.Popen([sys.executable, '-m', 'backend.app.worker'],
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        import uvicorn
        uvicorn.run('backend.app.main:create_app', factory=True, host=args.host, port=args.port)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == '__main__':
    main()
