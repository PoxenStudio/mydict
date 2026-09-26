from pydantic import BaseModel


class SystemInfoOut(BaseModel):
    version: str


class SystemTaskOut(BaseModel):
    id: int
    title: str
    stage: str | None = None
    done: int | None = None
    total: int | None = None
    elapsed_seconds: int


class SystemStatusOut(BaseModel):
    # starting / migrating / failed / ready；非 ready 时业务接口一律 503
    phase: str
    blocking: bool
    message: str | None = None
    tasks: list[SystemTaskOut]
    busy_notice: str | None = None
