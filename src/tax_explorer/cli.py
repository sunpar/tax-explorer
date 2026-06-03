from __future__ import annotations

import argparse
import csv
import sys

from tax_explorer import (
    PRETAX_DEDUCTION_MODE_CHOICES,
    PRETAX_DEDUCTION_MODE_MAX_AVAILABLE,
    TaxBurden,
    build_income_series,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate default 2026 US W-2 tax burden rows by income."
    )
    parser.add_argument("--start", type=str, default="0")
    parser.add_argument("--stop", type=str, default="500000")
    parser.add_argument("--step", type=str, default="10000")
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
    args = parser.parse_args(argv)

    rows = build_income_series(
        start=args.start,
        stop=args.stop,
        step=args.step,
        include_employer_payroll_tax=args.include_employer_payroll_tax,
        pretax_deduction_mode=args.pretax_deduction_mode,
        dependent_count=args.dependent_count,
    )
    write_csv(rows)
    return 0


def write_csv(rows: list[TaxBurden]) -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: getattr(row, field) for field in CSV_FIELDS})


if __name__ == "__main__":
    raise SystemExit(main())
