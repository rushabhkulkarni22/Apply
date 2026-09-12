from dataclasses import asdict
import math
import time
from job_applications.matching import JobSnapshot, MatchPolicy, canonical_skill, evaluate_job, fingerprint
from .locations import infer_job_location, location_record, selected_cities


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
        selections = profile.get('preferred_locations') or [profile.get('preferred_city', 'Pune')]
        cities = selected_cities(selections)
        job_place = infer_job_location(job.get('location', ''))
        job_coordinates = ((job.get('latitude'), job.get('longitude'))
                           if job.get('latitude') is not None and job.get('longitude') is not None
                           else job_place[2] if job_place and job_place[2] else None)
        selected_states = {value[6:] for value in selections if value.startswith('state:')}
        if job_place and (job_place[0] in selected_states or job_place[1] in cities):
            pass
        elif not job_coordinates:
            return stop('NEEDS_REVIEW', 'Job city is unknown; confirm whether it matches your selected locations')
        else:
            origins = [location_record(city)[2] for city in cities if location_record(city)]
            if not origins:
                return stop('NEEDS_REVIEW', 'Select at least one supported city for nearby matching')
            distance = min(distance_km(*origin, *job_coordinates) for origin in origins)
            result['distance_km'] = round(distance, 1)
            if distance > profile['radius_km']:
                return stop('REJECTED', f"Outside your {profile['radius_km']:g} km nearby area ({distance:.0f} km away)")
    if profile.get('strict_salary'):
        if job.get('salary_max_inr') is None:
            return stop('NEEDS_REVIEW', 'Salary is not disclosed')
        if job['salary_max_inr'] < profile['expected_ctc_inr']:
            return stop('REJECTED', 'Salary range is below your expectation')
    result['reason'] += '; experience and work-location preferences pass'
    return result
