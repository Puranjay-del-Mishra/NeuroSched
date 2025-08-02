import asyncio
import json
from api.schemas import SimulationConfig
from schedulers.fifo_scheduler import FIFOScheduler
from simulation.engine import SimulationEngine

async def main():
    # Config for quick test
    config = SimulationConfig(
        runtime_minutes=120,  # short run
        num_tenants=2,
        cluster_nodes=1,
        per_node_cpu=2,
        per_node_ram=2048,
        per_node_gpus=0,
        arrival_model="poisson",
        arrival_rate=8,
        duration_range=(3, 6),
        cpu_request_range=(1, 2),
        ram_request_range=(1024, 2048),
        gpu_request_range=(0, 0),
        priority_distribution={"low": 0.3, "med": 0.5, "high": 0.2},
        scheduler_choice="fifo",
        preemption_enabled=False,
    )
    
    scheduler = FIFOScheduler()
    engine = SimulationEngine(config, scheduler)

    # Run live and print snapshots
    async for snapshot in engine.run_live():
        print(json.dumps(snapshot, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
