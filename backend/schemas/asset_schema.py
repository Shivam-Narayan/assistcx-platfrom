# Installed libraries
from pydantic import BaseModel


class Changelog(BaseModel):
    content: str


class Version(BaseModel):
    version: str
