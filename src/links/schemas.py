from pydantic import BaseModel, HttpUrl, Field
from datetime import datetime
from typing import Optional

class LinkCreate(BaseModel):
    original_url: HttpUrl
    custom_alias: Optional[str] = Field(None, min_length=4, max_length=20)
    expires_at: Optional[datetime] = None
    project: Optional[str] = None

class LinkUpdate(BaseModel):
    original_url: HttpUrl

class LinkOut(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime]
    clicks: int
    last_used: Optional[datetime]

    class Config:
        from_attributes = True

class LinkStats(LinkOut):
    pass

class LinkExtend(BaseModel):
    days: int = Field(..., gt=0, le=365, description="Количество дней для продления")
    