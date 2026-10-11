"""Select checkpoints only from validation loss; no held-out or business data."""
from copy import deepcopy
import math


class ValidationSelection:
    def __init__(self, baseline, applications):
        self.applications = frozenset(applications)
        if not self.applications:
            raise ValueError("Validation applications must be declared")
        self.best_step = 0
        self.last_step = 0
        self.best = deepcopy(baseline)
        self._score(baseline)

    def _score(self, report):
        groups = report["by_application"]
        if set(groups) != self.applications:
            raise ValueError("Validation application coverage changed")
        values = [report["micro"], report["macro"], *groups.values()]
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                   and math.isfinite(value) and value >= 0 for value in values):
            raise ValueError("Validation losses must be finite and nonnegative")
        macro = sum(groups.values()) / len(groups)
        if not math.isclose(macro, report["macro"], rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("Validation macro loss mismatch")
        return macro

    def observe(self, step, report):
        if not isinstance(step, int) or isinstance(step, bool) or step <= self.last_step:
            raise ValueError("Validation steps must increase")
        score = self._score(report)
        self.last_step = step
        improved = score < self._score(self.best)
        if improved:
            self.best_step, self.best = step, deepcopy(report)
        return improved
