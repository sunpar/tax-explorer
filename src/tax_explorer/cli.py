from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from tax_explorer import (
    PRETAX_DEDUCTION_MODE_CHOICES,
    PRETAX_DEDUCTION_MODE_MAX_AVAILABLE,
    TaxBurden,
    build_income_series,
)
from tax_explorer.database import (
    DEFAULT_DATABASE_PATH,
    initialize_database,
    load_federal_tax_parameters,
    load_payroll_tax_parameters,
    load_pretax_deduction_parameters,
)


CSV_FIELDS = (
    "gross_income",
    "taxable_income",
    "federal_income_tax",
    "employee_social_security_tax",
    "employee_medicare_tax",
    "employee_additional_medicare_tax",
    "total_employee_payroll_tax",
    "total_employee_tax",
    "effective_employee_tax_rate",
    "employer_social_security_tax",
    "employer_medicare_tax",
    "total_employer_payroll_tax",
    "total_tax_with_employer_payroll",
    "marginal_employee_tax_rate",
    "marginal_tax_rate_with_employer_payroll",
    "employee_401k_contribution",
    "health_fsa_contribution",
    "dependent_care_fsa_contribution",
    "total_pretax_deductions",
)


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _finite_decimal_argument(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("must be a decimal number") from None
    if not parsed.is_finite():
        raise argparse.ArgumentTypeError("must be a decimal number")
    return parsed


def non_negative_decimal_argument(value: str) -> str:
    parsed = _finite_decimal_argument(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return value


def positive_decimal_argument(value: str) -> str:
    parsed = _finite_decimal_argument(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate US W-2 tax burden rows by income."
    )
    parser.add_argument("--start", type=non_negative_decimal_argument, default="0")
    parser.add_argument("--stop", type=non_negative_decimal_argument, default="500000")
    parser.add_argument("--step", type=positive_decimal_argument, default="10000")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--filing-status", default="single")
    parser.add_argument(
        "--secondary-income", type=non_negative_decimal_argument, default="0"
    )
    parser.add_argument(
        "--include-marginal-breakpoints",
        action="store_true",
        help="Include income rows where marginal tax rates change.",
    )
    parser.add_argument(
        "--include-employer-payroll-tax",
        action="store_true",
        help="Include employer Social Security and Medicare taxes in the output.",
    )
    parser.add_argument(
        "--pretax-deduction-mode",
        choices=PRETAX_DEDUCTION_MODE_CHOICES,
        default=PRETAX_DEDUCTION_MODE_MAX_AVAILABLE,
        help="Pre-tax payroll deduction usage model.",
    )
    parser.add_argument(
        "--dependent-count",
        type=non_negative_int,
        default=0,
        help="Number of dependents eligible for dependent-care FSA modeling.",
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="SQLite database path for tax parameters.",
    )
    args = parser.parse_args(argv)

    try:
        with initialize_database(args.database_path) as connection:
            federal = load_federal_tax_parameters(
                connection, args.year, args.filing_status
            )
            payroll = load_payroll_tax_parameters(connection, args.year)
            pretax_deductions = load_pretax_deduction_parameters(
                connection, args.year
            )
        rows = build_income_series(
            start=args.start,
            stop=args.stop,
            step=args.step,
            include_employer_payroll_tax=args.include_employer_payroll_tax,
            include_marginal_breakpoints=args.include_marginal_breakpoints,
            pretax_deduction_mode=args.pretax_deduction_mode,
            dependent_count=args.dependent_count,
            secondary_income=args.secondary_income,
            federal=federal,
            payroll=payroll,
            pretax_deductions=pretax_deductions,
        )
    except ValueError as exc:
        parser.error(str(exc))

    write_csv(rows)
    return 0


def write_csv(rows: list[TaxBurden]) -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: getattr(row, field) for field in CSV_FIELDS})


if __name__ == "__main__":
    raise SystemExit(main())
