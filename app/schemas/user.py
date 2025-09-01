from pydantic import BaseModel, EmailStr


class CreateUserIn(BaseModel):
    username: str
    email: EmailStr


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr