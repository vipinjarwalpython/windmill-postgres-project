from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class DepartmentRow(BaseModel):
    id: int
    source_row_id: int
    employee_name: str
    amount: Decimal
    record_date: date
    source_upload_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DepartmentDataResponse(BaseModel):
    department: str
    count: int
    rows: list[DepartmentRow]
