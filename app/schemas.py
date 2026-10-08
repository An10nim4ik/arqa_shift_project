from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TripCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    start: datetime
    end: datetime
    amount: int = Field(gt=0, strict=True)
    payment: Literal["cash", "card"]
    commission: int = Field(ge=0, strict=True)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Trip ID cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_trip(self):
        if self.start.tzinfo is None or self.start.utcoffset() is None:
            raise ValueError("Start time must contain an explicit UTC offset")
        if self.end.tzinfo is None or self.end.utcoffset() is None:
            raise ValueError("End time must contain an explicit UTC offset")
        if self.end <= self.start:
            raise ValueError("End time must be later than start time")
        if self.commission > self.amount:
            raise ValueError("Commission cannot exceed trip amount")
        return self


class TripOut(BaseModel):
    id: str
    start: datetime
    end: datetime
    amount: int
    payment: Literal["cash", "card"]
    commission: int


class Summary(BaseModel):
    trip_count: int
    revenue: int
    commission: int
    net: int
    cash: int
    card: int


class DayResponse(BaseModel):
    date: str
    summary: Summary
    trips: list[TripOut]


class InsertResponse(BaseModel):
    created: bool
    trip: TripOut
