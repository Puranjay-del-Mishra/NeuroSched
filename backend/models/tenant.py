# neurosched/models/tenant.py

from pydantic import BaseModel, Field
from typing import List
from api import Job


class Tenant(BaseModel):
    id: str
    submitted_jobs: List[Job] = Field(default_factory=list)
    completed_jobs: List[Job] = Field(default_factory=list)
    preempted_jobs: List[Job] = Field(default_factory=list)

    def avg_wait_time(self) -> float:
        if not self.completed_jobs:
            return 0.0
        total_wait = sum((job.start_time - job.arrival_time) for job in self.completed_jobs if job.start_time)
        return total_wait / len(self.completed_jobs)

    def total_jobs(self) -> int:
        return len(self.submitted_jobs)

    def throughput(self) -> int:
        return len(self.completed_jobs)
