from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable


MONEY = Decimal("0.01")
RATE_PRECISION = Decimal("0.0001")


def _decimal(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value))


def _money(value: Decimal | int | float | str) -> Decimal:
    return _decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class TaxBracket:
    lower_bound: Decimal
    rate: Decimal


@dataclass(frozen=True)
class FederalTaxParameters:
    tax_year: int
    filing_status: str
    standard_deduction: Decimal
    brackets: tuple[TaxBracket, ...]


@dataclass(frozen=True)
class PayrollTaxParameters:
    tax_year: int
    social_security_rate: Decimal
    social_security_wage_base: Decimal
    medicare_rate: Decimal
    additional_medicare_rate: Decimal
    additional_medicare_threshold_single: Decimal


@dataclass(frozen=True)
class TaxScenario:
    gross_income: Decimal
    include_employer_payroll_tax: bool = False


@dataclass(frozen=True)
class TaxBurden:
    gross_income: Decimal
    taxable_income: Decimal
    federal_income_tax: Decimal
    employee_social_security_tax: Decimal
    employee_medicare_tax: Decimal
    employee_additional_medicare_tax: Decimal
    total_employee_payroll_tax: Decimal
    total_employee_tax: Decimal
    effective_employee_tax_rate: Decimal
    employer_social_security_tax: Decimal
    employer_medicare_tax: Decimal
    total_employer_payroll_tax: Decimal
    total_tax_with_employer_payroll: Decimal


FEDERAL_2026_SINGLE = FederalTaxParameters(
    tax_year=2026,
    filing_status="single",
    standard_deduction=_money("16100"),
    brackets=(
        TaxBracket(_money("0"), Decimal("0.10")),
        TaxBracket(_money("12400"), Decimal("0.12")),
        TaxBracket(_money("50400"), Decimal("0.22")),
        TaxBracket(_money("105700"), Decimal("0.24")),
        TaxBracket(_money("201775"), Decimal("0.32")),
        TaxBracket(_money("256225"), Decimal("0.35")),
        TaxBracket(_money("640600"), Decimal("0.37")),
    ),
)

PAYROLL_2026 = PayrollTaxParameters(
    tax_year=2026,
    social_security_rate=Decimal("0.062"),
    social_security_wage_base=_money("184500"),
    medicare_rate=Decimal("0.0145"),
    additional_medicare_rate=Decimal("0.009"),
    additional_medicare_threshold_single=_money("200000"),
)


def calculate_tax_burden(
    scenario: TaxScenario,
    federal: FederalTaxParameters = FEDERAL_2026_SINGLE,
    payroll: PayrollTaxParameters = PAYROLL_2026,
) -> TaxBurden:
    gross_income = _money(scenario.gross_income)
    if gross_income < 0:
        raise ValueError("gross_income must be non-negative")

    taxable_income = max(_money("0"), gross_income - federal.standard_deduction)
    federal_income_tax = _calculate_progressive_tax(taxable_income, federal.brackets)

    social_security_wages = min(gross_income, payroll.social_security_wage_base)
    employee_social_security_tax = _money(
        social_security_wages * payroll.social_security_rate
    )
    employee_medicare_tax = _money(gross_income * payroll.medicare_rate)
    additional_medicare_wages = max(
        _money("0"), gross_income - payroll.additional_medicare_threshold_single
    )
    employee_additional_medicare_tax = _money(
        additional_medicare_wages * payroll.additional_medicare_rate
    )
    total_employee_payroll_tax = _money(
        employee_social_security_tax
        + employee_medicare_tax
        + employee_additional_medicare_tax
    )
    total_employee_tax = _money(federal_income_tax + total_employee_payroll_tax)
    effective_employee_tax_rate = _rate(total_employee_tax, gross_income)

    employer_social_security_tax = _money("0")
    employer_medicare_tax = _money("0")
    if scenario.include_employer_payroll_tax:
        employer_social_security_tax = employee_social_security_tax
        employer_medicare_tax = employee_medicare_tax

    total_employer_payroll_tax = _money(
        employer_social_security_tax + employer_medicare_tax
    )
    total_tax_with_employer_payroll = _money(
        total_employee_tax + total_employer_payroll_tax
    )

    return TaxBurden(
        gross_income=gross_income,
        taxable_income=taxable_income,
        federal_income_tax=federal_income_tax,
        employee_social_security_tax=employee_social_security_tax,
        employee_medicare_tax=employee_medicare_tax,
        employee_additional_medicare_tax=employee_additional_medicare_tax,
        total_employee_payroll_tax=total_employee_payroll_tax,
        total_employee_tax=total_employee_tax,
        effective_employee_tax_rate=effective_employee_tax_rate,
        employer_social_security_tax=employer_social_security_tax,
        employer_medicare_tax=employer_medicare_tax,
        total_employer_payroll_tax=total_employer_payroll_tax,
        total_tax_with_employer_payroll=total_tax_with_employer_payroll,
    )


def build_income_series(
    start: Decimal | int | float | str,
    stop: Decimal | int | float | str,
    step: Decimal | int | float | str,
    include_employer_payroll_tax: bool = False,
) -> list[TaxBurden]:
    current = _money(start)
    stop_amount = _money(stop)
    step_amount = _money(step)
    if step_amount <= 0:
        raise ValueError("step must be positive")
    if current < 0 or stop_amount < 0:
        raise ValueError("income bounds must be non-negative")

    rows: list[TaxBurden] = []
    while current <= stop_amount:
        rows.append(
            calculate_tax_burden(
                TaxScenario(
                    gross_income=current,
                    include_employer_payroll_tax=include_employer_payroll_tax,
                )
            )
        )
        current = _money(current + step_amount)
    return rows


def _calculate_progressive_tax(
    taxable_income: Decimal, brackets: Iterable[TaxBracket]
) -> Decimal:
    bracket_list = list(brackets)
    tax = Decimal("0")

    for index, bracket in enumerate(bracket_list):
        next_lower_bound = (
            bracket_list[index + 1].lower_bound
            if index + 1 < len(bracket_list)
            else None
        )
        bracket_ceiling = taxable_income if next_lower_bound is None else next_lower_bound
        taxable_at_rate = max(
            Decimal("0"), min(taxable_income, bracket_ceiling) - bracket.lower_bound
        )
        tax += taxable_at_rate * bracket.rate
        if taxable_income <= bracket_ceiling:
            break

    return _money(tax)


def _rate(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0.0000")
    return (numerator / denominator).quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)
