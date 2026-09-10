from pydantic import BaseModel, EmailStr, Field


class UserRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    email: EmailStr | None = None


class UserLoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserPublic(BaseModel):
    id: int
    username: str
    email: str | None = None
    status: str

    model_config = {"from_attributes": True}
