"""Shared schema building blocks."""

from decimal import Decimal
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer


def _num(v: Decimal) -> float:
    return float(v)


# Stored exactly as NUMERIC; sent to clients as a JSON number (Pydantic would otherwise emit a string).
Num = Annotated[Decimal, PlainSerializer(_num, return_type=float, when_used="json")]

Pct = Annotated[Decimal, Field(ge=0, le=100)]
NonNeg = Annotated[Decimal, Field(ge=0)]
Lat = Annotated[Decimal, Field(ge=-90, le=90)]
Lon = Annotated[Decimal, Field(ge=-180, le=180)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Notes = Annotated[str, Field(max_length=5000)]


class InputModel(BaseModel):
    """Request bodies: unknown fields are an error, so typos are never silently ignored."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OutputModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
