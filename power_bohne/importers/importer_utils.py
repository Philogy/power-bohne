from collections import defaultdict
from beancount.core.number import D


class MissedInstanceTracker:
    def __init__(self) -> None:
        self.totals = defaultdict(D)
        self.instances = []

    def add_instance(self, obj):
        self.instances.append(obj)

    def add_amount(self, category, amount):
        self.totals[category] += amount

    def reset(self):
        self.totals = defaultdict(D)
        self.instances = []

    def __iter__(self):
        return iter(self.instances)
