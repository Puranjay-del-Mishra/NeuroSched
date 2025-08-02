# neurosched/simulation/job_utils.py

from typing import List
from api import Job
from datetime import datetime


# Map string priorities to numeric values for easy comparison
def priority_value(priority: str) -> int:
    mapping = {"low": 1, "med": 2, "high": 3}
    return mapping.get(priority, 0)


def sort_ready_queue(jobs: List[Job], current_time: float) -> List[Job]:
    """
    Sort jobs by:
    1. Priority (high > med > low)
    2. Wait time (longer wait first)
    """
    return sorted(
        jobs,
        key=lambda job: (
            -priority_value(job.priority),               # Higher priority first
            -(current_time - job.arrival_time)           # Longer wait first
        )
    )
