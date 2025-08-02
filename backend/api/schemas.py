# neurosched/api/schemas.py

from pydantic import BaseModel, Field, conint, confloat
from typing import Optional, List, Dict, Literal, Tuple
import uuid


# -----------------------------
# 2. Simulation Config (User Input Parameters)
# -----------------------------
class SimulationConfig(BaseModel):
    runtime_seconds: conint(gt=0) = Field(..., description="Total simulation runtime in minutes")
    num_tenants: conint(gt=0) = Field(..., description="Number of tenants submitting jobs")

    # Cluster Config
    cluster_nodes: conint(gt=0) = Field(..., description="Number of cluster nodes")
    per_node_cpu: conint(gt=0) = Field(..., description="CPU cores per node")
    per_node_ram: conint(gt=0) = Field(..., description="RAM per node in MB")
    per_node_gpus: conint(ge=0) = Field(..., description="Number of GPUs per node")

    # Job Config
    arrival_model: Literal["poisson", "fixed"] = "poisson"
    arrival_rate: confloat(gt=0) = Field(..., description="Average job arrival rate per minute")
    duration_range: Tuple[conint(gt=0), conint(gt=0)] = Field(..., description="Min/Max job duration in minutes")

    cpu_request_range: Tuple[conint(gt=0), conint(gt=0)] = (1, 4)
    ram_request_range: Tuple[conint(gt=0), conint(gt=0)] = (512, 8192)
    gpu_request_range: Tuple[conint(ge=0), conint(ge=0)] = (0, 1)

    priority_distribution: Dict[Literal["low", "med", "high"], float] = Field(
        ..., example={"low": 0.3, "med": 0.5, "high": 0.2}
    )

    scheduler_choice: Literal["fifo", "stf", "rl"] = "fifo"
    preemption_enabled: bool = False


# -----------------------------
# 3. Job Model
# -----------------------------
class JobState(str):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PREEMPTED = "preempted"


class Job(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    cpu: conint(gt=0)
    ram: conint(gt=0)
    gpus: conint(ge=0)
    priority: Literal["low", "med", "high"]
    arrival_time: float
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    preemption_time: Optional[float] = None
    last_start_time: Optional[float] = None
    remaining_time: Optional[float] = None
    duration: float
    wait_time: Optional[float] = 0.0
    state: Literal["queued", "running", "completed", "preempted"] = "queued"


# -----------------------------
# 4. Node Model
# -----------------------------
class Node(BaseModel):
    id: str
    total_cpu: int
    total_ram: int
    total_gpus: int

    used_cpu: int = 0
    used_ram: int = 0
    used_gpus: int = 0

    running_jobs: List[str] = Field(default_factory=list)  # store Job IDs

    def can_allocate(self, job: Job) -> bool:
        return (
            self.total_cpu - self.used_cpu >= job.cpu
            and self.total_ram - self.used_ram >= job.ram
            and self.total_gpus - self.used_gpus >= job.gpus
        )

    def allocate(self, job: Job):
        if not self.can_allocate(job):
            raise ValueError(f"Node {self.id} cannot allocate job {job.id}")
        self.used_cpu += job.cpu
        self.used_ram += job.ram
        self.used_gpus += job.gpus
        self.running_jobs.append(job.id)

    def release(self, job: Job):
        if job.id in self.running_jobs:
            self.used_cpu -= job.cpu
            self.used_ram -= job.ram
            self.used_gpus -= job.gpus
            self.running_jobs.remove(job.id)
