"""Prevents markets from being emitted when their supporting statistics are sparse."""

def market_available(matches, required_fields, minimum_sample=20):
    usable = sum(all(match.get(field) is not None for field in required_fields) for match in matches)
    return usable >= minimum_sample, usable
