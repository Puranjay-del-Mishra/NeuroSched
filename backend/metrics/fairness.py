# backend/metrics/fairness.py

import math
from typing import Dict, List

def jains_fairness(values: List[float]) -> float:
    """
    Compute Jain's Fairness Index:
    F(x) = (sum(x_i))^2 / (n * sum(x_i^2))

    Args:
        values: list of resource allocations or performance metrics
    Returns:
        Fairness index in [0,1]
    """
    if not values or all(v == 0 for v in values):
        return 0.0

    numerator = sum(values) ** 2
    denominator = len(values) * sum(v ** 2 for v in values)

    return numerator / denominator if denominator > 0 else 0.0


def fairness_from_wait_times(avg_wait: Dict[str, float]) -> float:
    """
    Compute fairness across tenants given average wait times.
    Lower wait time = better service. 
    We'll invert values so that lower waits yield higher fairness.

    Args:
        avg_wait: dict {tenant_id: avg_wait_time}
    Returns:
        Jain's fairness index on inverted wait times
    """
    if not avg_wait:
        return 0.0

    # Invert waits so that smaller waits → larger value
    # Add epsilon to avoid division by zero
    epsilon = 1e-6
    inverted = [1.0 / (w + epsilon) for w in avg_wait.values()]
    return jains_fairness(inverted)
