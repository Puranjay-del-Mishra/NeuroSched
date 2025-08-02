# neurosched/simulation/event.py

from enum import Enum
from pydantic import BaseModel
from typing import Any
import itertools


class EventType(str, Enum):
    ARRIVAL = "arrival"
    COMPLETION = "completion"
    PREEMPTION = "preemption"
    SCHEDULING = "scheduling"


class Event(BaseModel):
    time: float
    type: EventType
    payload: Any   # Job, Node, etc.
    _counter: int = 0  # tie-breaker for heapq


# Unique sequence number for tie-breaking
_counter_gen = itertools.count()

def make_event(time: float, type: EventType, payload: Any):
    return (time, next(_counter_gen), Event(time=time, type=type, payload=payload))
