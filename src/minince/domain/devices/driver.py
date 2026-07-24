from __future__ import annotations

from typing import Protocol, runtime_checkable

from minince.domain.devices.facts import ConnectionResult, CurrentState, DeviceFacts
from minince.domain.network.config_plan import ConfigPlan, ExecutionResult, VerificationResult


@runtime_checkable
class NetworkDeviceDriver(Protocol):
    def test_connection(self) -> ConnectionResult: ...

    def get_facts(self) -> DeviceFacts: ...

    def get_current_state(self, intent: object) -> CurrentState: ...

    def build_plan(
        self,
        intent: object,
        current_state: CurrentState,
    ) -> ConfigPlan: ...

    def apply_plan(self, plan: ConfigPlan) -> ExecutionResult: ...

    def verify(
        self,
        intent: object,
    ) -> VerificationResult: ...
