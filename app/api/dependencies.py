from fastapi import Request
from app.core.di import AppContainer
from app.application.orchestrator import CommandBus


def get_container(request: Request) -> AppContainer:
    return request.app.state.container  # type: ignore[attr-defined]


def get_command_bus(request: Request) -> CommandBus:
    return get_container(request).command_bus