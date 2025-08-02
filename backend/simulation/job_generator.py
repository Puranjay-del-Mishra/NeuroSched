import random, threading, time
from queue import Queue
from api import Job
import logging

class JobGenerator:
    def __init__(self, config, tenants, job_queue: Queue):
        self.config = config
        self.tenants = tenants
        self.job_queue = job_queue
        self.running = False

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._generate_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if hasattr(self, "thread"):
            self.thread.join()

    def _generate_loop(self):
        logging.info("JobGenerator thread started")
        start_wall = time.time()

        while self.running and time.time()-start_wall < self.config.runtime_seconds:
            # sample next inter-arrival time in minutes
            interval = random.expovariate(self.config.arrival_rate)

            # sleep for the inter-arrival interval (converted to seconds)
            time.sleep(interval * 60)

            if not self.running or (time.time() - start_wall) >= self.config.runtime_seconds:
                break

            dur = random.uniform(*self.config.duration_range)

            tenant = random.choice(self.tenants)
            job = Job(
                tenant_id=tenant.id,
                cpu=random.randint(*self.config.cpu_request_range),
                ram=random.randint(*self.config.ram_request_range),
                gpus=random.randint(*self.config.gpu_request_range),
                priority=random.choices(
                    population=list(self.config.priority_distribution.keys()),
                    weights=list(self.config.priority_distribution.values()),
                    k=1
                )[0],
                arrival_time=time.time(),
                duration= dur,
                remaining_time = dur
            )
            tenant.submitted_jobs.append(job)

            logging.debug(f"Attempting to enqueue Job {job.id[:6]} for {tenant.id} at {time.time():.2f} minutes")
            self.job_queue.put(job)
            logging.debug(f"Successfully enqueued Job {job.id[:6]} for {tenant.id}")


        logging.info("JobGenerator thread finished")


