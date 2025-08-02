# backend/simulation/engine.py

import random
import time
from queue import Queue, Empty
from typing import List
from api import SimulationConfig, Job, Node
from models import Tenant
from simulation.event import EventType, make_event
from simulation.event_queue import EventQueue
from simulation.job_generator import JobGenerator
from utils.job_utils import sort_ready_queue
from metrics.fairness import fairness_from_wait_times
import logging
import heapq
import asyncio

class SimulationEngine:
    def __init__(self, config: SimulationConfig, scheduler):
        self.config = config
        self.scheduler = scheduler
        self.clock = 0.0
        self.event_queue = EventQueue()
        self.global_ready_queue: List[Job] = []
        self.running_jobs: List[tuple] = []
        self.tenants = [Tenant(id=f"tenant-{i+1}") for i in range(config.num_tenants)]
        self.cluster = [
            Node(
                id=f"node-{i+1}",
                total_cpu=config.per_node_cpu,
                total_ram=config.per_node_ram,
                total_gpus=config.per_node_gpus,
            )
            for i in range(config.cluster_nodes)
        ]
        # Shared thread-safe job buffer
        self.job_queue = Queue() #generator populates this 
        self.job_generator = JobGenerator(config, self.tenants, self.job_queue) #generator

    # ------------------------------
    # Public Simulation Loop
    # ------------------------------
    def run(self):
        self.job_generator.start()
        logging.info("SimulationEngine started")

        start = time.time()
        while time.time() - start <= self.config.runtime_seconds:
            now = time.time()

            # Step 1: ingest new jobs
            self._ingest_new_jobs()

            # Step 2: process scheduled events (arrivals & scheduling only)
            while not self.event_queue.is_empty() and self.event_queue.peek().time <= now:
                event = self.event_queue.pop()
                logging.debug(f"Processing event {event.type} at sim time {now:.2f}")
                self._handle_event(event)

            # Step 3: update remaining times for running jobs
            for idx, (finish_time, job, node) in enumerate(list(self.running_jobs)):
                if job.state == "running" and job.last_start_time:
                    elapsed = now - job.last_start_time
                    job.remaining_time = max(0.0, job.duration - elapsed)

            # Step 4: handle running job completions
            self._handle_running_jobs()

            # Optional: yield CPU briefly for realism
            time.sleep(0.05)

        self.job_generator.stop()
        logging.info("SimulationEngine finished")
        return self._collect_results()

    # ------------------------------
    # Ingest Jobs Safely
    # ------------------------------
    def _ingest_new_jobs(self):
        while True:
            try:
                job = self.job_queue.get_nowait()
                now = time.time()
                job.arrival_time = now  # override to current tick
                self.event_queue.push(make_event(now, EventType.ARRIVAL, job))
                logging.debug(f"[INGEST] Queued Job {job.id[:6]} for arrival at {now:.2f}")
            except Empty:
                break

    # ------------------------------
    # Event Handlers
    # ------------------------------
    def _handle_event(self, event):
        logging.debug(f"Event arrived: {event}")
        if event.type == EventType.ARRIVAL:
            self._handle_arrival(event.payload)
        elif event.type == EventType.SCHEDULING:
            self._handle_scheduling()
        elif event.type == EventType.PREEMPTION:
            self._handle_preemption(event.payload)

    def _handle_arrival(self, job: Job):
        logging.debug(
            f"Job {job.id[:6]} ARRIVED (Tenant={job.tenant_id}, "
            f"Priority={job.priority}, Duration={job.duration:.2f})"
        )
        now = time.time()
        job.arrival_time = now
        job.last_start_time = None       # not yet started
        job.preemption_time = None       # not yet preempted
        self.global_ready_queue.append(job)
        # trigger scheduling immediately
        self.event_queue.push(make_event(now, EventType.SCHEDULING, None))

    def _handle_scheduling(self):
        if not self.global_ready_queue:
            return

        sorted_jobs = sort_ready_queue(self.global_ready_queue, time.time())
        self.scheduler.schedule(
            self.cluster, sorted_jobs, self.global_ready_queue, self.running_jobs
        )

    def _handle_preemption(self, job: Job):
        logging.debug(
            f"Job {job.id[:6]} PREEMPTED (Tenant={job.tenant_id}, "
            f"Remaining={job.duration:.2f})"
        )
        # Just enqueue the job back for scheduling
        self.global_ready_queue.append(job)
        self.event_queue.push(make_event(time.time(), EventType.SCHEDULING, None))

    def _handle_completion(self, job: Job, node, finish_time: float):
        """Mark job as completed, release resources, and update tenant stats."""
        if job in node.running_jobs:
            node.running_jobs.remove(job)

        node.release(job)
        job.state = "completed"
        job.end_time = finish_time
        job.remaining_time = 0.0

        tenant = next(t for t in self.tenants if t.id == job.tenant_id)
        tenant.completed_jobs.append(job)

        logging.debug(
            f"Job {job.id[:6]} COMPLETED at {finish_time:.2f} "
            f"(Tenant={job.tenant_id}, Wait={job.wait_time:.2f})"
        )

    async def run_live(self, stop_flag=None):
        self.job_generator.start()
        start_wall = time.time()
        last_state = None  

        while time.time() - start_wall <= self.config.runtime_seconds:
            if stop_flag and stop_flag():
                logging.info("Stop requested — ending simulation early")
                break

            self._ingest_new_jobs()

            while not self.event_queue.is_empty() and self.event_queue.peek().time <= time.time():
                event = self.event_queue.pop()
                logging.debug(f"Processing event {event.type} at sim time {time.time():.2f}")
                self._handle_event(event)

            self._handle_running_jobs()

            state = {
                "queue_len": len(self.global_ready_queue),
                "running_jobs": [(j.id, j.tenant_id) for _, j, _ in self.running_jobs],
                "completed_jobs": sum(len(t.completed_jobs) for t in self.tenants),
            }

            if state != last_state:
                snapshot = {
                    "time": round(time.time() - start_wall, 2),
                    **state,
                    "running_jobs": [
                        {
                            "id": j.id,
                            "tenant": j.tenant_id,
                            "cpu": j.cpu,
                            "start": round(j.start_time - start_wall, 2) if j.start_time else None,
                        }
                        for _, j, _ in self.running_jobs
                    ],
                }
                yield snapshot
                last_state = state

            await asyncio.sleep(0.05)

        self.job_generator.stop()

    def _handle_running_jobs(self):
        """Update running jobs' remaining times and complete those that have finished."""
        now = time.time()

        updated_heap = []
        while self.running_jobs:
            finish_time, job, node = heapq.heappop(self.running_jobs)

            if job.state == "running" and job.last_start_time:
                elapsed = now - job.last_start_time
                job.remaining_time = max(0.0, job.remaining_time - elapsed)

            if job.remaining_time <= 0.0:
                # Job finished — handle completion
                self._handle_completion(job, node, now)
            else:
                # Still running — recompute new finish_time
                new_finish_time = now + job.remaining_time
                heapq.heappush(updated_heap, (new_finish_time, job, node))

        self.running_jobs = updated_heap
        heapq.heapify(self.running_jobs)
    # ------------------------------
    # Results Collection
    # ------------------------------
    def _collect_results(self):
        throughput = {t.id: t.throughput() for t in self.tenants}
        avg_wait = {t.id: t.avg_wait_time() for t in self.tenants}
        fairness = fairness_from_wait_times(avg_wait)

        return {
            "utilization": {},  # TODO: add resource utilization metrics
            "throughput": throughput,
            "avg_wait": avg_wait,
            "fairness": fairness,
        }
