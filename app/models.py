from pydantic import BaseModel, Field, field_validator
import re
from typing import Literal

E164 = re.compile(r'^\+[1-9][0-9]{7,14}$')


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=120)
    language: str = Field(default='English', max_length=64)
    instructions: str = Field(min_length=10, max_length=4000)


class PlanRequest(BaseModel):
    message: str = Field(min_length=5, max_length=2500)
    phone: str = ''
    agent_id: str = 'receptionist'
    contact_id: str | None = None


class PlanEdit(BaseModel):
    goal: str = Field(min_length=5, max_length=1200)
    agenda: list[str] = Field(min_length=1, max_length=10)
    script: str = Field(min_length=5, max_length=2000)

    @field_validator('agenda')
    @classmethod
    def clean_agenda(cls, agenda):
        if any(not s.strip() or len(s) > 300 for s in agenda):
            raise ValueError('Each agenda item must contain 1–300 characters')
        return agenda


class CallRequest(BaseModel):
    plan_id: str
    confirm: bool = False
    voice_engine: Literal["openai_live", "deepgram"] | None = None


class PreviewTurn(BaseModel):
    text: str = Field(min_length=1, max_length=800)


def valid_phone(phone: str) -> bool:
    return bool(E164.fullmatch(phone))
