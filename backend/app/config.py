from dataclasses import dataclass
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    database_url: str = 'sqlite:///./runtime/app.db'
    storage_dir: str = 'runtime/resumes'
    resume_storage: str = 'filesystem'
    app_origin: str = 'http://localhost:8000'
    environment: str = 'development'
    demo_enabled: bool = True
    google_client_id: str = ''
    owner_emails: str = ''
    razorpay_key_id: str = ''
    razorpay_key_secret: str = ''
    razorpay_webhook_secret: str = ''
    provider_url: str = ''
    provider_token: str = ''
    job_feed_url: str = ''
    sales_enabled: bool = False
    session_seconds: int = 86400

    def is_owner(self, email):
        allowed = {value.strip().lower() for value in self.owner_emails.split(',') if value.strip()}
        return bool(email and email.strip().lower() in allowed)

    @classmethod
    def from_env(cls):
        defaults = cls()
        values = {}
        for name in cls.__dataclass_fields__:
            value = os.getenv(name.upper())
            if value is not None:
                old = getattr(defaults, name)
                values[name] = value.lower() in ('1', 'true', 'yes') if isinstance(old, bool) else int(value) if isinstance(old, int) else value
        if not values.get('app_origin') and os.getenv('RENDER_EXTERNAL_URL'):
            values['app_origin'] = os.environ['RENDER_EXTERNAL_URL']
        result = cls(**values)
        if result.resume_storage not in ('filesystem', 'database'):
            raise ValueError('RESUME_STORAGE must be filesystem or database')
        if result.environment == 'production':
            if result.demo_enabled or not result.google_client_id or not result.app_origin.startswith('https://'):
                raise ValueError('Production requires DEMO_ENABLED=false, GOOGLE_CLIENT_ID and HTTPS APP_ORIGIN')
            if result.provider_url and not result.provider_url.startswith('https://'):
                raise ValueError('Production provider must use HTTPS')
        if result.sales_enabled and not all((result.provider_url, result.razorpay_key_id, result.razorpay_key_secret, result.razorpay_webhook_secret)):
            raise ValueError('Sales require a configured delivery provider and Razorpay credentials')
        return result
