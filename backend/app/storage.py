"""Private resume storage supporting local files and ephemeral cloud runtimes."""
from pathlib import Path
import secrets


def save_resume(settings, user_id, filename, content):
    if settings.resume_storage == 'database':
        return '', content
    folder = Path(settings.storage_dir) / user_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (secrets.token_hex(16) + Path(filename).suffix.lower())
    path.write_bytes(content)
    return str(path.resolve()), None


def read_resume(resume):
    if resume.content is not None:
        return bytes(resume.content)
    if resume.path:
        return Path(resume.path).read_bytes()
    raise FileNotFoundError('Resume content is unavailable')


def resume_exists(resume):
    return resume.content is not None or bool(resume.path and Path(resume.path).is_file())


def delete_resume_file(settings, resume):
    if not resume.path:
        return
    path = Path(resume.path).resolve()
    if not path.is_relative_to(Path(settings.storage_dir).resolve()):
        raise ValueError('Storage path could not be verified')
    path.unlink(missing_ok=True)
