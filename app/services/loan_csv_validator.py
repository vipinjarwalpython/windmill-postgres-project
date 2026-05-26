"""Validate that an uploaded file is actually a loan-pipeline CSV.

The Windmill flow ``u/admin/loan_pipeline`` reads the CSV with these columns:
``id, department, employee_name, amount, date``.  If the file isn't a CSV
with those columns, the flow either crashes mid-step or silently inserts
zero rows.  Validating upfront in FastAPI means the user sees a precise
error before the workflow is even triggered.
"""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from fastapi import HTTPException, status


# Column names the loan flow expects in the CSV header. Order doesn't matter,
# but every name must be present.
LOAN_REQUIRED_COLUMNS: tuple[str, ...] = (
    "id",
    "department",
    "employee_name",
    "amount",
    "date",
)

# Departments the pipeline understands. Rows with anything else get silently
# dropped by the Windmill flow, so we warn early.
LOAN_VALID_DEPARTMENTS: tuple[str, ...] = ("finance", "hr", "sales")

# How much of the file to peek at while validating. 64 KB is plenty to find
# the header and a handful of sample rows even on a 1 GB CSV.
_PREVIEW_BYTES = 64 * 1024

# How many data rows to scan for department validation. Keep it bounded so a
# malicious file with millions of bogus rows can't make validation slow.
_SAMPLE_ROWS = 200


class LoanCsvError(HTTPException):
    """HTTPException tagged so callers can distinguish validation errors from
    other failures (e.g. to remove the on-disk file before re-raising)."""

    def __init__(self, message: str) -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _human_extension_list(allowed: list[str]) -> str:
    extras = [e for e in allowed if e.lower() != ".csv"]
    return ", ".join(sorted(extras)) if extras else ""


def validate_loan_csv(path: Path, allowed_extensions: list[str]) -> None:
    """Raise :class:`LoanCsvError` if ``path`` isn't a parseable loan CSV.

    The check is intentionally cheap: read up to 64 KB, parse it with the
    stdlib ``csv`` module, confirm the header has every required column,
    and confirm at least one data row exists.
    """
    ext = path.suffix.lower()

    # 1. Extension check. The loan pipeline can only consume CSVs even if the
    # storage policy is permissive (.txt / .pdf / .json).
    if ext != ".csv":
        other = _human_extension_list(allowed_extensions)
        if other:
            hint = (
                f" Storage policy also allows {other}, but the loan workflow "
                "can only process .csv right now."
            )
        else:
            hint = ""
        raise LoanCsvError(
            f"Unsupported file type '{ext}'. Upload a .csv file with columns: "
            f"{', '.join(LOAN_REQUIRED_COLUMNS)}.{hint}"
        )

    # 2. UTF-8 readability. PDFs and Excel files saved as .csv will fail here.
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            sample = f.read(_PREVIEW_BYTES)
    except UnicodeDecodeError:
        raise LoanCsvError(
            "File is not valid UTF-8 text. Re-save the CSV with UTF-8 "
            "encoding (in Excel: 'CSV UTF-8' export). Binary files like "
            ".xlsx or .pdf renamed to .csv are not accepted."
        )

    if not sample.strip():
        raise LoanCsvError("File is empty.")

    # 3. Parse as CSV and validate header.
    reader = csv.reader(StringIO(sample))
    try:
        header = next(reader)
    except StopIteration:
        raise LoanCsvError("CSV has no header row.")

    header_norm = [h.strip().lower() for h in header]
    if not any(header_norm):
        raise LoanCsvError("CSV header is blank — first row must be column names.")

    missing = [col for col in LOAN_REQUIRED_COLUMNS if col not in header_norm]
    if missing:
        raise LoanCsvError(
            "CSV is missing required column(s): "
            f"{', '.join(missing)}. Expected header: "
            f"{', '.join(LOAN_REQUIRED_COLUMNS)}. Got: "
            f"{', '.join(header) if header else '(empty)'}."
        )

    # 4. At least one data row.
    try:
        first_row = next(reader)
    except StopIteration:
        raise LoanCsvError("CSV has only a header — no data rows to ingest.")

    if len(first_row) < len(LOAN_REQUIRED_COLUMNS):
        raise LoanCsvError(
            f"First data row has only {len(first_row)} field(s); expected at "
            f"least {len(LOAN_REQUIRED_COLUMNS)} to match the header."
        )

    # 5. Sample-check departments. Reject early if every row in the preview
    # has an unknown department — the pipeline would just drop them.
    dept_idx = header_norm.index("department")
    seen_dept: set[str] = set()
    rows_scanned = 1
    invalid_depts: set[str] = set()
    for row in reader:
        if rows_scanned >= _SAMPLE_ROWS:
            break
        rows_scanned += 1
        if len(row) <= dept_idx:
            continue
        d = (row[dept_idx] or "").strip().lower()
        if not d:
            continue
        if d in LOAN_VALID_DEPARTMENTS:
            seen_dept.add(d)
        else:
            invalid_depts.add(d)

    # Include the first row in the dept survey too
    first_dept = (first_row[dept_idx] if len(first_row) > dept_idx else "").strip().lower()
    if first_dept in LOAN_VALID_DEPARTMENTS:
        seen_dept.add(first_dept)
    elif first_dept:
        invalid_depts.add(first_dept)

    if not seen_dept and invalid_depts:
        raise LoanCsvError(
            "CSV has no rows belonging to a known department. "
            f"Valid departments: {', '.join(LOAN_VALID_DEPARTMENTS)}. "
            f"Saw: {', '.join(sorted(invalid_depts))[:200]}."
        )
