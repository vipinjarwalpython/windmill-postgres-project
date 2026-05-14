from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class IngestRow(BaseModel):
    department: str = Field(pattern="^(finance|hr|sales)$")
    source_row_id: int
    employee_name: str
    amount: Decimal
    record_date: date


class IngestRequest(BaseModel):
    upload_id: int
    rows: list[IngestRow]


class IngestResponse(BaseModel):
    upload_id: int
    inserted: dict[str, int]
    total: int
