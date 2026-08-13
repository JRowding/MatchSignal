from math import log

def brier_score(predictions: list[tuple[float, int]]) -> float | None:
    return sum((probability - outcome) ** 2 for probability, outcome in predictions) / len(predictions) if predictions else None

def log_loss(predictions: list[tuple[float, int]]) -> float | None:
    if not predictions: return None
    epsilon = 1e-12
    return -sum(outcome * log(max(probability, epsilon)) + (1 - outcome) * log(max(1 - probability, epsilon)) for probability, outcome in predictions) / len(predictions)

def calibration(predictions: list[tuple[float, int]]) -> list[dict]:
    buckets = []
    for lower in range(50, 100, 10):
        values = [(p, o) for p, o in predictions if lower / 100 <= p < (lower + 10) / 100 or (lower == 90 and p == 1)]
        if values:
            buckets.append({"bucket": f"{lower}-{lower + 9}%", "predicted": sum(p for p, _ in values) / len(values), "actual": sum(o for _, o in values) / len(values), "count": len(values)})
    return buckets
