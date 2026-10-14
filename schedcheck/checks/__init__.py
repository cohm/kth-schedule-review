"""Check registry.

A check is a function `check(ctx: Context) -> list[Issue]`. Each check
declares which review types it applies to; reviews run every registered
check whose `applies_to` contains their type. See docs/ADDING_A_CHECK.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..config import Config
from ..io.studyplan import StudyPlan
from ..model import Issue
from ..term import TermData


@dataclass
class YearPlan:
    program: str
    year: int | None
    specialization: str | None
    cohort: str | None
    plan: StudyPlan | None
    note: str = ""             # why the plan is missing / how reliable it is


@dataclass
class Context:
    review: str                          # "program" | "course"
    new: TermData
    old: TermData | None
    config: Config
    plans: dict[tuple[str, int | None], YearPlan] = field(default_factory=dict)
    old_plans: dict[tuple[str, int | None], YearPlan] = field(default_factory=dict)
    courses: set[str] | None = None      # restrict to these courses (course review)

    def wants(self, code: str) -> bool:
        return self.courses is None or code in self.courses


@dataclass
class CheckSpec:
    name: str
    func: Callable[[Context], list[Issue]]
    applies_to: tuple[str, ...]
    description: str


REGISTRY: list[CheckSpec] = []


def register(name: str, applies_to: tuple[str, ...], description: str):
    def deco(func):
        REGISTRY.append(CheckSpec(name, func, applies_to, description))
        return func
    return deco


def run_checks(ctx: Context) -> list[Issue]:
    # Import modules for their registration side effect.
    from . import coverage, structure, exams, teaching, dataquality  # noqa: F401
    issues: list[Issue] = []
    for spec in REGISTRY:
        if ctx.review in spec.applies_to:
            issues.extend(spec.func(ctx))
    return issues
