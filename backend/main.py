# backend/main.py

from api.schemas import SimulationConfig
from schedulers.fifo_scheduler import FIFOScheduler
from simulation.engine import SimulationEngine

import logging

# Configure logging: show thread name + timestamp
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    # Example config
    config = SimulationConfig(
    runtime_seconds=300,
    num_tenants=2,
    cluster_nodes=1,          # only ONE node
    per_node_cpu=2,           # small CPU capacity
    per_node_ram=2048,        # 2GB RAM
    per_node_gpus=0,          # no GPUs
    arrival_model="poisson",
    arrival_rate=8,           # high arrival rate -> heavy load
    duration_range=(3, 6),    # jobs take 3–6 minutes
    cpu_request_range=(1, 2), # jobs can eat up all CPUs
    ram_request_range=(1024, 2048),  # half to all RAM
    gpu_request_range=(0, 0),       # disable GPUs to simplify
    priority_distribution={"low": 0.3, "med": 0.5, "high": 0.2},
    scheduler_choice="fifo",
    preemption_enabled=False,
    )

    # Initialize scheduler and engine
    scheduler = FIFOScheduler()
    engine = SimulationEngine(config, scheduler)

    # Run simulation
    results = engine.run()

    # Print results
    print("=== Simulation Results ===")
    for tenant_id, throughput in results["throughput"].items():
        print(f"Tenant {tenant_id}:")
        print(f"  Throughput: {throughput}")
        print(f"  Avg Wait: {results['avg_wait'][tenant_id]:.2f}")

if __name__ == "__main__":
    main()
