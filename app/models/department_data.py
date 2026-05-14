from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class _DepartmentRowMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_row_id: Mapped[int] = mapped_column(Integer, nullable=False)
    employee_name: Mapped[str] = mapped_column(String(120), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    record_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_upload_id: Mapped[int] = mapped_column(ForeignKey("file_uploads.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FinanceData(_DepartmentRowMixin, Base):
    __tablename__ = "finance_data"


class HRData(_DepartmentRowMixin, Base):
    __tablename__ = "hr_data"


class SalesData(_DepartmentRowMixin, Base):
    __tablename__ = "sales_data"


DEPARTMENT_MODELS = {
    "finance": FinanceData,
    "hr": HRData,
    "sales": SalesData,
}
