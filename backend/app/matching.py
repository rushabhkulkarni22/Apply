from dataclasses import asdict
import math
import time
from job_applications.matching import JobSnapshot, MatchPolicy, canonical_skill, evaluate_job, fingerprint


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = p2-p1, math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 6371 * 2 * math.asin(min(1, math.sqrt(a)))


def match(profile, job):
    policy = MatchPolicy(tuple(profile['target_titles']), tuple(profile['selected_skills']), profile['minimum_skills'])
    result = asdict(evaluate_job(JobSnapshot(job['title'], job['description']), profile['skills'], policy))
    result['profile_hash'] = fingerprint(profile)
    result['job_hash'] = fingerprint(job)
    result['distance_km'] = None
    def stop(status, reason):
        result.update(status=status, reason=reason)
        return result
    if result['status'] != 'ELIGIBLE':
        return result
    if job.get('expires_at') and job['expires_at'] <= time.time():
        return stop('REJECTED', 'Job has expired')
    if job.get('minimum_experience') is None:
        return stop('NEEDS_REVIEW', 'Required experience is unknown; add verified job details')
    if job['minimum_experience'] > profile['experience_years']:
        return stop('REJECTED', f"Requires {job['minimum_experience']:g} years; profile has {profile['experience_years']:g}")
    required = {canonical_skill(s) for s in job.get('required_skills', [])}
    missing = required - {canonical_skill(s) for s in profile['skills']}
    if missing:
        return stop('REJECTED', 'Missing required skills: ' + ', '.join(sorted(missing)))
    mode = job.get('work_mode', 'unknown')
    if mode == 'unknown':
        return stop('NEEDS_REVIEW', 'Work mode is unknown')
    if mode not in profile['work_modes']:
        return stop('REJECTED', 'Work mode does not match your preference')
    if mode != 'remote':
        if job.get('latitude') is None or job.get('longitude') is None:
            return stop('NEEDS_REVIEW', 'Job coordinates are unavailable for radius filtering')
        distance = distance_km(profile['latitude'], profile['longitude'], job['latitude'], job['longitude'])
        result['distance_km'] = round(distance, 1)
        if distance > profile['radius_km']:
            return stop('REJECTED', f"Outside your {profile['radius_km']:g} km radius ({distance:.0f} km away)")
    if profile.get('strict_salary'):
        if job.get('salary_max_inr') is None:
            return stop('NEEDS_REVIEW', 'Salary is not disclosed')
        if job['salary_max_inr'] < profile['expected_ctc_inr']:
            return stop('REJECTED', 'Salary range is below your expectation')
    result['reason'] += '; experience and work-location preferences pass'
    return result
