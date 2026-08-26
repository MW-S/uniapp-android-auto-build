from dataclasses import dataclass, field


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
