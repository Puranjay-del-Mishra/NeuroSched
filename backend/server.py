from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import logging

from simulation.engine import SimulationEngine
from schedulers.fifo_scheduler import FIFOScheduler
from api.schemas import SimulationConfig
from store.redis_store import RedisStore  # new import
from schedulers.stf_scheduler import ShortestTimeFirstScheduler

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    force=True,  # override uvicorn's setup for child threads too
)

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = None          # holds current SimulationEngine
stop_signal = False    # flag to stop live simulation
last_results = None    # cached results for frontend after run
store = RedisStore()   # Redis persistence


def ensure_tuple(body, key):
    """Convert frontend arrays to tuples for Pydantic."""
    if key in body and isinstance(body[key], list):
        body[key] = tuple(body[key])


@app.post("/start-simulation")
async def start_simulation(request: Request):
    """
    Receive config from frontend and spin up a SimulationEngine.
    """
    global engine, stop_signal, last_results
    body = await request.json()

    # Convert list ranges to tuples
    for key in ["duration_range", "cpu_request_range", "ram_request_range", "gpu_request_range"]:
        ensure_tuple(body, key)

    config = SimulationConfig(**body)  # now expects runtime_seconds
    if config.scheduler_choice == "fifo":
        scheduler = FIFOScheduler()
    elif config.scheduler_choice == "stf":
        scheduler = ShortestTimeFirstScheduler()
    else:
        return {"error": f"Unsupported scheduler: {config.scheduler_choice}"}
    engine = SimulationEngine(config, scheduler)
    stop_signal = False
    last_results = None

    # Clear previous run in Redis
    await store.clear_run()

    return {"status": "simulation started"}


@app.post("/stop-simulation")
async def stop_simulation():
    """
    Stop a currently running simulation.
    """
    global stop_signal
    stop_signal = True
    return {"status": "simulation stopping"}


@app.get("/results")
async def get_results():
    """
    Fetch last simulation results for frontend display.
    """
    global last_results
    redis_results = await store.load_results()
    if redis_results:
        return redis_results

    if last_results is None:
        return {"status": "no results yet"}
    return last_results


@app.post("/clear-results")
async def clear_results():
    """
    Clear persisted results and plots from Redis.
    """
    await store.clear_run()
    return {"status": "cleared"}

@app.get("/history")
async def get_history():
    """
    Fetch stored live data points for charts.
    """
    return await store.load_updates()

@app.websocket("/ws/simulation")
async def simulation_ws(ws: WebSocket):
    global engine, stop_signal, last_results
    await ws.accept()

    if engine is None:
        await ws.send_text(json.dumps({"error": "Simulation not started"}))
        await ws.close()
        return

    try:
        async for update in engine.run_live(stop_flag=lambda: stop_signal):
            if stop_signal:
                break

            total_cpu = sum(node.total_cpu for node in engine.cluster)
            used_cpu = sum(
                j["cpu"] for _, job, _ in engine.running_jobs
                for j in [{"cpu": job.cpu}]
            )
            update["cpu_util"] = round((used_cpu / total_cpu) * 100) if total_cpu > 0 else 0

            # save update to Redis
            await store.save_update(update)

            # send to frontend
            await ws.send_text(json.dumps(update))

    finally:
        if engine:
            last_results = engine._collect_results()
            await store.save_results(last_results)
        await ws.close()
