import re


# A focused catalogue of Indian employment hubs. Coordinates are application
# metadata used for approximate nearby-city matching; applicants never enter them.
INDIA_LOCATIONS = {
    'Andhra Pradesh': {
        'Visakhapatnam': (17.6868, 83.2185), 'Vijayawada': (16.5062, 80.6480),
        'Tirupati': (13.6288, 79.4192),
    },
    'Assam': {'Guwahati': (26.1445, 91.7362)},
    'Bihar': {'Patna': (25.5941, 85.1376)},
    'Chandigarh': {'Chandigarh': (30.7333, 76.7794)},
    'Chhattisgarh': {'Raipur': (21.2514, 81.6296)},
    'Delhi': {'Delhi NCR': (28.6139, 77.2090), 'New Delhi': (28.6139, 77.2090)},
    'Goa': {'Panaji': (15.4909, 73.8278)},
    'Gujarat': {
        'Ahmedabad': (23.0225, 72.5714), 'Gandhinagar': (23.2156, 72.6369),
        'Surat': (21.1702, 72.8311), 'Vadodara': (22.3072, 73.1812), 'Rajkot': (22.3039, 70.8022),
    },
    'Haryana': {
        'Gurugram': (28.4595, 77.0266), 'Faridabad': (28.4089, 77.3178),
        'Ambala': (30.3782, 76.7767),
    },
    'Himachal Pradesh': {'Shimla': (31.1048, 77.1734)},
    'Jharkhand': {'Ranchi': (23.3441, 85.3096), 'Jamshedpur': (22.8046, 86.2029)},
    'Karnataka': {
        'Bengaluru': (12.9716, 77.5946), 'Mysuru': (12.2958, 76.6394),
        'Mangaluru': (12.9141, 74.8560), 'Hubballi': (15.3647, 75.1240),
    },
    'Kerala': {
        'Kochi': (9.9312, 76.2673), 'Thiruvananthapuram': (8.5241, 76.9366),
        'Kozhikode': (11.2588, 75.7804),
    },
    'Madhya Pradesh': {'Indore': (22.7196, 75.8577), 'Bhopal': (23.2599, 77.4126)},
    'Maharashtra': {
        'Mumbai': (19.0760, 72.8777), 'Navi Mumbai': (19.0330, 73.0297),
        'Pune': (18.5204, 73.8567), 'Thane': (19.2183, 72.9781),
        'Nagpur': (21.1458, 79.0882), 'Nashik': (19.9975, 73.7898),
    },
    'Odisha': {'Bhubaneswar': (20.2961, 85.8245)},
    'Punjab': {'Mohali': (30.7046, 76.7179), 'Ludhiana': (30.9010, 75.8573)},
    'Rajasthan': {'Jaipur': (26.9124, 75.7873), 'Udaipur': (24.5854, 73.7125)},
    'Tamil Nadu': {
        'Chennai': (13.0827, 80.2707), 'Coimbatore': (11.0168, 76.9558),
        'Madurai': (9.9252, 78.1198), 'Tiruchirappalli': (10.7905, 78.7047),
    },
    'Telangana': {'Hyderabad': (17.3850, 78.4867), 'Warangal': (17.9689, 79.5941)},
    'Uttar Pradesh': {
        'Noida': (28.5355, 77.3910), 'Greater Noida': (28.4744, 77.5040),
        'Ghaziabad': (28.6692, 77.4538), 'Lucknow': (26.8467, 80.9462),
    },
    'Uttarakhand': {'Dehradun': (30.3165, 78.0322)},
    'West Bengal': {'Kolkata': (22.5726, 88.3639)},
}

ALIASES = {
    'bangalore': 'Bengaluru', 'bombay': 'Mumbai', 'calcutta': 'Kolkata',
    'gurgaon': 'Gurugram', 'delhi': 'Delhi NCR', 'ncr': 'Delhi NCR',
    'trivandrum': 'Thiruvananthapuram', 'cochin': 'Kochi',
}


def normalize(value):
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()


def catalogue():
    return [{'state': state, 'cities': list(cities)} for state, cities in INDIA_LOCATIONS.items()]


def location_record(city):
    wanted = ALIASES.get(normalize(city), city)
    key = normalize(wanted)
    for state, cities in INDIA_LOCATIONS.items():
        for name, coordinates in cities.items():
            if normalize(name) == key:
                return state, name, coordinates
    return None


def selected_cities(selections):
    result = []
    for selection in selections:
        if selection.startswith('state:'):
            state = selection[6:]
            result.extend(INDIA_LOCATIONS.get(state, {}).keys())
        elif location_record(selection):
            result.append(location_record(selection)[1])
    return list(dict.fromkeys(result))


def infer_job_location(text):
    value = normalize(text or '')
    if not value:
        return None
    for alias, city in ALIASES.items():
        if re.search(rf'\b{re.escape(alias)}\b', value):
            return location_record(city)
    for state, cities in INDIA_LOCATIONS.items():
        for city, coordinates in cities.items():
            if re.search(rf'\b{re.escape(normalize(city))}\b', value):
                return state, city, coordinates
        if re.search(rf'\b{re.escape(normalize(state))}\b', value):
            return state, None, None
    return None
