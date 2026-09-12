from typing import Literal
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ProfileInput(StrictModel):
    full_name: str = Field(min_length=1, max_length=150)
    phone: str = Field(default='', max_length=40)
    email: str = Field(default='', max_length=255)
    skills: list[str] = Field(min_length=3, max_length=100)
    target_titles: list[str] = Field(min_length=1, max_length=30)
    selected_skills: list[str] = Field(min_length=3, max_length=30)
    minimum_skills: int = Field(default=3, ge=3, le=30)
    experience_years: float = Field(ge=0, le=60)
    notice_days: int = Field(default=30, ge=0, le=365)
    current_ctc_inr: int = Field(default=0, ge=0, le=100000000)
    expected_ctc_inr: int = Field(default=0, ge=0, le=100000000)
    preferred_city: str = Field(default='Pune', max_length=100)
    latitude: float = Field(default=18.5204, ge=-90, le=90)
    longitude: float = Field(default=73.8567, ge=-180, le=180)
    radius_km: float = Field(default=50, ge=1, le=20000)
    work_modes: list[Literal['remote', 'hybrid', 'onsite']] = Field(default=['remote', 'hybrid'], min_length=1)
    strict_salary: bool = False
    confirmed: bool = True

    @field_validator('skills', 'target_titles', 'selected_skills')
    @classmethod
    def nonempty(cls, values):
        if any(not v.strip() or len(v) > 100 for v in values):
            raise ValueError('Use nonempty titles/skills of at most 100 characters')
        return list(dict.fromkeys(v.strip() for v in values))

    @model_validator(mode='after')
    def valid_skills(self):
        from job_applications.matching import canonical_skill
        selected = {canonical_skill(s) for s in self.selected_skills}
        if self.minimum_skills > len(selected) or not selected <= {canonical_skill(s) for s in self.skills}:
            raise ValueError('Selected skills must be confirmed profile skills; minimum cannot exceed distinct selections')
        return self


class JobInput(StrictModel):
    external_id: str = Field(min_length=1, max_length=200)
    source: str = Field(default='manual', min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    url: str = Field(max_length=1500)
    description: str = Field(min_length=1, max_length=30000)
    location: str = Field(default='', max_length=150)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    work_mode: Literal['remote', 'hybrid', 'onsite', 'unknown'] = 'unknown'
    minimum_experience: float | None = Field(default=None, ge=0, le=60)
    salary_max_inr: int | None = Field(default=None, ge=0, le=100000000)
    required_skills: list[str] = Field(default=[], max_length=100)
    expires_at: float | None = None

    @field_validator('url')
    @classmethod
    def valid_url(cls, value):
        parsed = urlparse(value)
        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Job URL must be a normal HTTP(S) URL')
        return value


class JobsInput(StrictModel):
    jobs: list[JobInput] = Field(min_length=1, max_length=100)


class RunInput(StrictModel):
    resume_id: str
    limit: int = Field(default=10, ge=1, le=40)
    daily: bool = False
    authorized: bool = False
    job_ids: list[str] = Field(default=[], max_length=100)


class GoogleInput(StrictModel):
    credential: str = Field(min_length=1, max_length=10000)


class VerifyPayment(StrictModel):
    razorpay_order_id: str = Field(max_length=100)
    razorpay_payment_id: str = Field(max_length=100)
    razorpay_signature: str = Field(max_length=200)
