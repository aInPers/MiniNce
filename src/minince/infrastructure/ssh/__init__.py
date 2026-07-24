from __future__ import annotations

from minince.infrastructure.ssh.base import SSHConfig, SSHConnection
from minince.shared.exceptions import DeviceConnectionError

_SSH_BACKENDS: dict[str, type[SSHConnection]] = {}


def register_ssh_backend(name: str, backend_class: type[SSHConnection]) -> None:
    _SSH_BACKENDS[name] = backend_class


def create_ssh_connection(config: SSHConfig, backend: str | None = None) -> SSHConnection:
    if backend is None:
        backend = _detect_backend(config)

    backend_class = _SSH_BACKENDS.get(backend)
    if backend_class is None:
        raise DeviceConnectionError(
            f"SSH backend not available: {backend}",
            details={"available": list(_SSH_BACKENDS.keys())},
        )
    return backend_class(config)  # type: ignore[call-arg]


def list_ssh_backends() -> list[str]:
    return list(_SSH_BACKENDS.keys())


def _detect_backend(config: SSHConfig) -> str:
    if config.host == "mock" or config.host.startswith("mock:"):
        return "mock"

    import importlib.util

    if importlib.util.find_spec("paramiko") is not None:
        return "paramiko"

    if importlib.util.find_spec("netmiko") is not None:
        return "netmiko"

    return "mock"


def _ensure_backends_loaded() -> None:
    if _SSH_BACKENDS:
        return
    from minince.infrastructure.ssh.mock_connection import MockSSHConnection
    register_ssh_backend("mock", MockSSHConnection)

    try:
        from minince.infrastructure.ssh.paramiko_connection import ParamikoSSHConnection
        register_ssh_backend("paramiko", ParamikoSSHConnection)
    except ImportError:
        pass

    try:
        from minince.infrastructure.ssh.netmiko_connection import NetmikoSSHConnection
        register_ssh_backend("netmiko", NetmikoSSHConnection)
    except ImportError:
        pass


_ensure_backends_loaded()
