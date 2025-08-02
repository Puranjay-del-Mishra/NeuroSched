import logging
import heapq
import time
from typing import List
from api.schemas import Job, Node

class ShortestTimeFirstScheduler:
    def schedule(self, cluster, sorted_jobs, global_ready_queue, running_jobs):
        logging.debug("=== Cluster State Before Scheduling (SRTF) ===")
        for node in cluster:
            logging.debug(
                f"{node.id}: CPU {node.used_cpu}/{node.total_cpu}, "
                f"RAM {node.used_ram}/{node.total_ram}, "
                f"GPUs {node.used_gpus}/{node.total_gpus}, "
                f"Running Jobs: {len(node.running_jobs)}"
            )

        # Sort jobs by (remaining_time, -priority_value)
        sorted_jobs = sorted(
            sorted_jobs,
            key=lambda job: (job.remaining_time, -self.priority_value(job.priority)),
        )

        for job in list(sorted_jobs):  # safe copy
            allocated = False
            for node in cluster:
                if node.can_allocate(job):
                    self._allocate_job(node, job, global_ready_queue, running_jobs)
                    allocated = True
                    break

            if not allocated:
                # Try preemption: check for a worse (longer or lower-priority) job
                victim_tuple = self.find_victim(job, running_jobs, cluster)
                if victim_tuple:
                    self.preempt_and_allocate(
                        victim_tuple, job, cluster, global_ready_queue, running_jobs
                    )
                    allocated = True

            if not allocated:
                logging.debug(f"Job {job.id[:6]} waiting (no resources)")

        logging.debug("=== Cluster State After Scheduling (SRTF) ===")
        for node in cluster:
            logging.debug(
                f"{node.id}: CPU {node.used_cpu}/{node.total_cpu}, "
                f"RAM {node.used_ram}/{node.total_ram}, "
                f"GPUs {node.used_gpus}/{node.total_gpus}, "
                f"Running Jobs: {len(node.running_jobs)}"
            )

    def _allocate_job(self, node: Node, job: Job, global_ready_queue: List[Job], running_jobs: list):
        node.allocate(job)

        now = time.time()
        if job.start_time is None:
            # First time running
            job.start_time = now
            job.wait_time = now - job.arrival_time
        else:
            # Resumed after preemption
            if job.preemption_time:
                job.wait_time += now - job.preemption_time
                job.preemption_time = None

        job.last_start_time = now
        job.state = "running"
        if job in global_ready_queue:
            global_ready_queue.remove(job)

        finish_time = now + job.remaining_time
        heapq.heappush(running_jobs, (finish_time, job, node))

        logging.debug(
            f"Allocated Job {job.id[:6]} (Tenant={job.tenant_id}, "
            f"CPU={job.cpu}, RAM={job.ram}) "
            f"to {node.id}, finishes at {finish_time:.2f}, "
            f"remaining={job.remaining_time:.2f}"
        )

    def find_victim(self, incoming_job, running_jobs, cluster):
        """Find a running job to preempt if the incoming one is shorter (or equal + higher priority)."""
        for finish_time, victim_job, node in list(running_jobs):
            if (
                incoming_job.remaining_time < victim_job.remaining_time
                or (
                    incoming_job.remaining_time == victim_job.remaining_time
                    and self.priority_value(incoming_job.priority)
                    > self.priority_value(victim_job.priority)
                )
            ):
                if (
                    node.used_cpu - victim_job.cpu + incoming_job.cpu <= node.total_cpu
                    and node.used_ram - victim_job.ram + incoming_job.ram <= node.total_ram
                    and node.used_gpus - victim_job.gpus + incoming_job.gpus <= node.total_gpus
                ):
                    return (finish_time, victim_job, node)
        return None

    def preempt_and_allocate(self, victim_tuple, new_job, cluster, global_ready_queue, running_jobs):
        finish_time, victim_job, node = victim_tuple

        running_jobs.remove(victim_tuple)
        heapq.heapify(running_jobs)

        node.release(victim_job)

        now = time.time()
        elapsed = now - victim_job.last_start_time
        victim_job.remaining_time = max(0, victim_job.remaining_time - elapsed)

        victim_job.state = "preempted"
        victim_job.preemption_time = now
        global_ready_queue.append(victim_job)

        logging.info(
            f"Preempted Job {victim_job.id[:6]} (Tenant={victim_job.tenant_id}) "
            f"for shorter Job {new_job.id[:6]} (Tenant={new_job.tenant_id}), "
            f"remaining victim={victim_job.remaining_time:.2f}"
        )

        self._allocate_job(node, new_job, global_ready_queue, running_jobs)

    @staticmethod
    def priority_value(priority: str) -> int:
        mapping = {"low": 1, "med": 2, "high": 3}
        return mapping.get(priority, 0)
