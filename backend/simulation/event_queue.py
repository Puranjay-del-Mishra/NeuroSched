# neurosched/simulation/event_queue.py

import heapq
from typing import List, Tuple
from .event import Event, make_event, EventType


class EventQueue:
    def __init__(self):
        self._queue: List[Tuple[float, int, Event]] = []

    def push(self, event: Tuple[float, int, Event]):
        heapq.heappush(self._queue, event)

    def pop(self) -> Event:
        if not self._queue:
            return None
        return heapq.heappop(self._queue)[2]

    def peek(self) -> Event:
        return self._queue[0][2] if self._queue else None

    def is_empty(self) -> bool:
        return not self._queue
