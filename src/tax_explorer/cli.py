from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from tax_explorer import (
    FILING_STATUS_CHOICES,
    MONEY,
    PRETAX_DEDUCTION_MODE_CHOICES,
    PRETAX_DEDUCTION_MODE_MAX_AVAILABLE,
    TaxBurden,
    build_income_series,
)
from tax_explorer.database import (
    DEFAULT_DATABASE_PATH,
    initialize_database,
    is_tax_year_available,
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
DEFAULT_TAX_YEAR = 2026


def non_negative_int(value: str) -> int:
    if "_" in value:
        raise argparse.ArgumentTypeError("must be a whole number") from None
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a whole number") from None
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _finite_decimal_argument(value: str) -> Decimal:
    if "_" in value:
        raise argparse.ArgumentTypeError("must be a decimal number") from None
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


def positive_money_increment_argument(value: str) -> str:
    parsed = _finite_decimal_argument(value)
    try:
        increment = parsed.quantize(MONEY, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("must fit cents precision") from None
    if increment <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def _rounded_money_argument(value: str) -> Decimal | None:
    try:
        return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _money_comparison_argument(value: str) -> Decimal:
    rounded = _rounded_money_argument(value)
    return rounded if rounded is not None else Decimal(value)


def _validate_roundable_money_arguments(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    fields: tuple[tuple[str, str], ...],
) -> None:
    for attribute, flag in fields:
        if _rounded_money_argument(getattr(args, attribute)) is None:
            parser.error(f"argument {flag}: must fit cents precision")


def _can_prevalidate_arguments(args: argparse.Namespace) -> bool:
    return args.year == DEFAULT_TAX_YEAR and args.filing_status in FILING_STATUS_CHOICES


def validate_secondary_income_arguments(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> None:
    if not _can_prevalidate_arguments(args):
        return

    stop = _money_comparison_argument(args.stop)
    secondary_income = _money_comparison_argument(args.secondary_income)
    if secondary_income == 0:
        return

    if args.filing_status != "married_joint" and secondary_income > 0:
        parser.error("secondary_income is only supported for married_joint")
    _validate_roundable_money_arguments(
        args,
        parser,
        (("secondary_income", "--secondary-income"),),
    )
    if secondary_income > stop:
        parser.error("secondary_income cannot exceed stop")


def validate_income_range_arguments(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> None:
    if not _can_prevalidate_arguments(args):
        return

    start = _money_comparison_argument(args.start)
    stop = _money_comparison_argument(args.stop)
    if start > stop:
        parser.error("start must be less than or equal to stop")
    _validate_roundable_money_arguments(
        args,
        parser,
        (("start", "--start"), ("stop", "--stop")),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate US W-2 tax burden rows by income."
    )
    parser.add_argument("--start", type=non_negative_decimal_argument, default="0")
    parser.add_argument("--stop", type=non_negative_decimal_argument, default="500000")
    parser.add_argument(
        "--step", type=positive_money_increment_argument, default="10000"
    )
    parser.add_argument("--year", type=non_negative_int, default=DEFAULT_TAX_YEAR)
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
    validate_income_range_arguments(args, parser)
    validate_secondary_income_arguments(args, parser)

    try:
        with initialize_database(args.database_path) as connection:
            federal = load_federal_tax_parameters(
                connection, args.year, args.filing_status
            )
            payroll = load_payroll_tax_parameters(connection, args.year)
            pretax_deductions = load_pretax_deduction_parameters(
                connection, args.year
            )
            if not is_tax_year_available(connection, args.year):
                raise ValueError(f"No tax parameters for {args.year}")
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
