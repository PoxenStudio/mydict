from pydantic import BaseModel


class SystemInfoOut(BaseModel):
    version: str
