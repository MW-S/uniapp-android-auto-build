import os
import sys
from dataclasses import dataclass, field


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root_dir() -> str:
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class StepResult:
    ok: bool
    log: str
    data: dict = field(default_factory=dict)

    @classmethod
    def ok_result(cls, log: str, **data) -> "StepResult":
        return cls(ok=True, log=log, data=dict(data))

    @classmethod
    def fail_result(cls, log: str, **data) -> "StepResult":
        return cls(ok=False, log=log, data=dict(data))
