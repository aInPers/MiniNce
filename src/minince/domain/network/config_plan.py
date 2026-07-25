from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from minince.shared.enums import RiskLevel


@dataclass
class ConfigStep:
    name: str
    command: str
    description: str = ""


@dataclass
class ConfigPlan:
    device_id: int
    feature: str
    intent: dict[str, Any]
    current_state: dict[str, Any]
    commands: list[str] = field(default_factory=list)
    verify_commands: list[str] = field(default_factory=list)
    changed: bool = True
    risk_level: RiskLevel = RiskLevel.LOW
    warnings: list[str] = field(default_factory=list)
    steps: list[ConfigStep] = field(default_factory=list)
    # 本次明确新增/修改配置对应的回滚命令；第一版仅覆盖本次变更，非完整精确回滚
    rollback_commands: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "feature": self.feature,
            "intent": self.intent,
            "current_state": self.current_state,
            "commands": self.commands,
            "verify_commands": self.verify_commands,
            "changed": self.changed,
            "risk_level": self.risk_level.value,
            "warnings": self.warnings,
            "steps": [
                {"name": s.name, "command": s.command, "description": s.description}
                for s in self.steps
            ],
            "rollback_commands": self.rollback_commands,
        }


@dataclass
class ExecutionResult:
    success: bool
    command_outputs: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "command_outputs": self.command_outputs,
            "error_message": self.error_message,
        }


@dataclass
class VerificationResult:
    success: bool
    verification_outputs: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "verification_outputs": self.verification_outputs,
            "error_message": self.error_message,
            "details": self.details,
        }
