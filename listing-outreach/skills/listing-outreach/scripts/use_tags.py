#!/usr/bin/env python3
"""OSM tag vocabulary per retail use — shared by the proximity and local-operator scripts.

Its own module on purpose. `classify_proximity.py` parses sys.argv at import time, so
importing it to borrow this table ran its CLI and printed its usage instead. Keeping
the data in a file with no side effects means either script can read it, and the two
never drift apart into slightly different definitions of "dentist".

Keys are the shorthand accepted by `--uses`. Values are OSM tag values, `|`-separated,
under the tag key that actually carries them: a dentist is tagged both
`amenity=dentist` (older convention) and `healthcare=dentist` (current), so both are
queried or half the market goes missing.
"""

USE_TAGS = {
    "food":      {"amenity": "fast_food|restaurant|cafe|bank"},
    "coffee":    {"amenity": "cafe|fast_food"},
    "bank":      {"amenity": "bank|bureau_de_change"},
    "dentist":   {"amenity": "dentist", "healthcare": "dentist"},
    "medical":   {"amenity": "clinic|doctors", "healthcare": "doctor|clinic|centre"},
    "vet":       {"amenity": "veterinary", "healthcare": "veterinary"},
    "pharmacy":  {"amenity": "pharmacy", "shop": "chemist"},
    "fitness":   {"amenity": "gym", "shop": "sports", "leisure": "fitness_centre"},
    "childcare": {"amenity": "childcare|kindergarten"},
    "carwash":   {"amenity": "car_wash"},
    "auto":      {"amenity": "fuel", "shop": "car_repair|tyres|car_parts"},
    "salon":     {"shop": "hairdresser|beauty|nails"},
    "grocery":   {"shop": "supermarket|convenience|greengrocer"},
    "liquor":    {"shop": "alcohol|wine"},
    "pet":       {"shop": "pet|pet_grooming", "amenity": "veterinary"},
}

TAG_KEYS = ("amenity", "shop", "healthcare", "leisure")


def resolve(uses):
    """['dentist'] -> {'amenity': {'dentist'}, 'healthcare': {'dentist'}, ...}"""
    out = {k: set() for k in TAG_KEYS}
    unknown = [u for u in uses if u not in USE_TAGS]
    if unknown:
        raise KeyError(f"unknown use(s) {', '.join(unknown)}; "
                       f"known: {', '.join(sorted(USE_TAGS))}")
    for u in uses:
        for k, v in USE_TAGS[u].items():
            out[k].update(x for x in v.split("|") if x)
    return out
