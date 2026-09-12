"""Pure, conservative eligibility rules; no browser, model, or filesystem work."""
from dataclasses import dataclass
import hashlib
import json
import re


ALIASES = {
    'pyspark': ('pyspark', 'py spark'),
    'aws': ('aws', 'amazon web services'),
    'sql': ('sql', 'structured query language'),
    'python': ('python', 'python 3', 'python3'),
}


@dataclass(frozen=True)
class MatchPolicy:
    allowed_titles: tuple[str, ...]
    selected_skills: tuple[str, ...]
    minimum_skills: int = 3
    version: str = '1'

    def __post_init__(self):
        if not self.allowed_titles or any(not t.strip() for t in self.allowed_titles):
            raise ValueError('At least one explicit allowed title is required')
        skills = {canonical_skill(s) for s in self.selected_skills}
        if '' in skills or type(self.minimum_skills) is not int or not 3 <= self.minimum_skills <= len(skills):
            raise ValueError('Select at least three distinct skills and a valid minimum >= 3')


@dataclass(frozen=True)
class JobSnapshot:
    title: str
    description: str


@dataclass(frozen=True)
class MatchDecision:
    status: str
    reason: str
    matched_skills: tuple[str, ...] = ()
    evidence: tuple[tuple[str, str], ...] = ()


def normalize(text):
    return re.sub(r'\s+', ' ', text.casefold()).strip()


def canonical_skill(skill):
    normalized = normalize(skill)
    return next((key for key, names in ALIASES.items() if normalized in names), normalized)


def title_matches(title, policy):
    # Explicit complete titles prevent "Data Engineer / ML Engineer" from passing.
    return normalize(title) in {normalize(t) for t in policy.allowed_titles}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def evaluate_job(job, candidate_skills, policy):
    if not job.title.strip():
        return MatchDecision('NEEDS_REVIEW', 'Job title could not be established')
    if not title_matches(job.title, policy):
        return MatchDecision('REJECTED', f'Role is not approved: {job.title}')
    if not job.description.strip():
        return MatchDecision('NEEDS_REVIEW', 'Full job description is unavailable')
    supported = {canonical_skill(s) for s in candidate_skills}
    selected = {canonical_skill(s) for s in policy.selected_skills}
    evidence = []
    ambiguous = False
    for skill in sorted(selected & supported):
        names = ALIASES.get(skill, (skill,))
        pattern = r'(?<!\w)(?:' + '|'.join(re.escape(n) for n in names) + r')(?!\w)'
        for sentence in re.split(r'[\n.!?;]+', job.description):
            if re.search(pattern, sentence, re.I):
                # Conservative: negation or instruction-like text needs human review.
                if re.search(r'\b(no|not|without|ignore|disregard)\b', sentence, re.I):
                    ambiguous = True
                    continue
                evidence.append((skill, sentence.strip()))
                break
    matched = tuple(s for s, _ in evidence)
    if ambiguous:
        return MatchDecision('NEEDS_REVIEW', 'Ambiguous skill evidence needs review', matched, tuple(evidence))
    if len(matched) < policy.minimum_skills:
        return MatchDecision('REJECTED', f'Only {len(matched)} distinct selected resume skills match; need {policy.minimum_skills}', matched, tuple(evidence))
    return MatchDecision('ELIGIBLE', f'Approved role and {len(matched)} distinct selected resume skills match', matched, tuple(evidence))
