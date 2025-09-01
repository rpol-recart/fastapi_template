from fastapi import APIRouter, Depends, Header
from typing import Optional
from app.schemas.user import CreateUserIn, UserOut
from app.application.orchestrator import CommandBus
from app.domain.commands import CreateUserCommand, GetUserCommand
from app.api.dependencies import get_command_bus

router = APIRouter(prefix="/api", tags=["api"])


@router.post("/users", response_model=UserOut)
def create_user(payload: CreateUserIn, bus: CommandBus = Depends(get_command_bus), x_request_id: Optional[str] = Header(default=None)):
    cmd = CreateUserCommand(username=payload.username, email=payload.email)
    result = bus.execute(cmd, request_id=x_request_id)
    return UserOut(id=result.id, username=result.username, email=result.email)


@router.get("/users/{user_id}", response_model=UserOut | None)
def get_user(user_id: int, bus: CommandBus = Depends(get_command_bus), x_request_id: Optional[str] = Header(default=None)):
    cmd = GetUserCommand(user_id=user_id)
    result = bus.execute(cmd, request_id=x_request_id)
    if result is None:
        return None
    return UserOut(id=result.id, username=result.username, email=result.email)