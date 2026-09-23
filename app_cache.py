"""Bounded, process-local daily cache. Nothing is written to disk."""
from collections import OrderedDict
from copy import deepcopy
from threading import Condition
import time

DAY = 24 * 60 * 60


class DailyCache:
    def __init__(self, limit=4096):
        self.entries = OrderedDict()
        self.pending = set()
        self.condition = Condition()
        self.generation = 0
        self.limit = limit

    def get(self, key, read):
        with self.condition:
            while key in self.pending:
                self.condition.wait()
            hit = self.entries.get(key)
            if hit and time.time() - hit[0] < DAY:
                self.entries.move_to_end(key)
                return deepcopy(hit[1])
            self.entries.pop(key, None)
            generation = self.generation
            self.pending.add(key)
        try:
            value = read()
            with self.condition:
                if generation == self.generation:
                    self.entries[key] = (time.time(), deepcopy(value))
                    while len(self.entries) > self.limit:
                        self.entries.popitem(last=False)
            return value
        finally:
            with self.condition:
                self.pending.discard(key)
                self.condition.notify_all()

    def clear(self, partition=None):
        with self.condition:
            self.generation += 1
            if partition is None:
                self.entries.clear()
            else:
                for key in list(self.entries):
                    if key[0] == partition:
                        del self.entries[key]

    def oldest(self, partition):
        with self.condition:
            return min((stamp for key, (stamp, _) in self.entries.items()
                        if key[0] == partition and time.time() - stamp < DAY), default=None)
