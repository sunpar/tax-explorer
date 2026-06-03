from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Mapping


MONEY = Decimal("0.01")
RATE_PRECISION = Decimal("0.0001")
MAX_INCOME_SERIES_ROWS = 2001


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
    additional_medicare_thresholds: Mapping[str, Decimal] = field(default_factory=dict)


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
    marginal_employee_tax_rate: Decimal
    employer_social_security_tax: Decimal
    employer_medicare_tax: Decimal
    total_employer_payroll_tax: Decimal
    total_tax_with_employer_payroll: Decimal
    marginal_tax_rate_with_employer_payroll: Decimal


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
    additional_medicare_thresholds={
        "single": _money("200000"),
        "married_joint": _money("250000"),
        "married_separate": _money("125000"),
        "head_of_household": _money("200000"),
    },
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
    additional_medicare_threshold = _additional_medicare_threshold(federal, payroll)
    additional_medicare_wages = max(
        _money("0"), gross_income - additional_medicare_threshold
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
    marginal_employee_tax_rate = _marginal_employee_tax_rate(
        gross_income, federal, payroll
    )

    employer_social_security_tax = _money("0")
    employer_medicare_tax = _money("0")
    marginal_employer_payroll_tax_rate = Decimal("0")
    if scenario.include_employer_payroll_tax:
        employer_social_security_tax = employee_social_security_tax
        employer_medicare_tax = employee_medicare_tax
        marginal_employer_payroll_tax_rate = _marginal_employer_payroll_tax_rate(
            gross_income, payroll
        )

    total_employer_payroll_tax = _money(
        employer_social_security_tax + employer_medicare_tax
    )
    total_tax_with_employer_payroll = _money(
        total_employee_tax + total_employer_payroll_tax
    )
    marginal_tax_rate_with_employer_payroll = (
        marginal_employee_tax_rate + marginal_employer_payroll_tax_rate
    ).quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)

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
        marginal_employee_tax_rate=marginal_employee_tax_rate,
        employer_social_security_tax=employer_social_security_tax,
        employer_medicare_tax=employer_medicare_tax,
        total_employer_payroll_tax=total_employer_payroll_tax,
        total_tax_with_employer_payroll=total_tax_with_employer_payroll,
        marginal_tax_rate_with_employer_payroll=marginal_tax_rate_with_employer_payroll,
    )


def build_income_series(
    start: Decimal | int | float | str,
    stop: Decimal | int | float | str,
    step: Decimal | int | float | str,
    include_employer_payroll_tax: bool = False,
    include_marginal_breakpoints: bool = False,
    federal: FederalTaxParameters = FEDERAL_2026_SINGLE,
    payroll: PayrollTaxParameters = PAYROLL_2026,
) -> list[TaxBurden]:
    current = _money(start)
    stop_amount = _money(stop)
    step_amount = _money(step)
    if step_amount <= 0:
        raise ValueError("step must be positive")
    if current < 0 or stop_amount < 0:
        raise ValueError("income bounds must be non-negative")
    if current > stop_amount:
        raise ValueError("start must be less than or equal to stop")

    incomes: set[Decimal] = set()
    while current <= stop_amount:
        incomes.add(current)
        current = _money(current + step_amount)

    if include_marginal_breakpoints:
        incomes.add(stop_amount)
        incomes.update(
            income
            for income in _marginal_rate_change_incomes(federal, payroll)
            if current_range_contains(income, start_amount=_money(start), stop_amount=stop_amount)
        )

    if len(incomes) > MAX_INCOME_SERIES_ROWS:
        raise ValueError(
            f"income-series supports at most {MAX_INCOME_SERIES_ROWS} rows"
        )

    return [
        calculate_tax_burden(
            TaxScenario(
                gross_income=income,
                include_employer_payroll_tax=include_employer_payroll_tax,
            ),
            federal=federal,
            payroll=payroll,
        )
        for income in sorted(incomes)
    ]


def current_range_contains(
    income: Decimal, start_amount: Decimal, stop_amount: Decimal
) -> bool:
    return start_amount <= income <= stop_amount


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


def _marginal_employee_tax_rate(
    gross_income: Decimal,
    federal: FederalTaxParameters,
    payroll: PayrollTaxParameters,
) -> Decimal:
    rate = _federal_marginal_rate(gross_income, federal)
    if gross_income < payroll.social_security_wage_base:
        rate += payroll.social_security_rate
    rate += payroll.medicare_rate
    if gross_income >= _additional_medicare_threshold(federal, payroll):
        rate += payroll.additional_medicare_rate
    return rate.quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)


def _marginal_employer_payroll_tax_rate(
    gross_income: Decimal, payroll: PayrollTaxParameters
) -> Decimal:
    rate = payroll.medicare_rate
    if gross_income < payroll.social_security_wage_base:
        rate += payroll.social_security_rate
    return rate.quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)


def _federal_marginal_rate(
    gross_income: Decimal, federal: FederalTaxParameters
) -> Decimal:
    taxable_income = max(_money("0"), gross_income - federal.standard_deduction)
    if taxable_income == 0 and gross_income < federal.standard_deduction:
        return Decimal("0")

    selected_rate = federal.brackets[0].rate
    for bracket in federal.brackets:
        if taxable_income >= bracket.lower_bound:
            selected_rate = bracket.rate
        else:
            break
    return selected_rate


def _marginal_rate_change_incomes(
    federal: FederalTaxParameters, payroll: PayrollTaxParameters
) -> set[Decimal]:
    incomes = {
        federal.standard_deduction + bracket.lower_bound
        for bracket in federal.brackets
    }
    incomes.add(payroll.social_security_wage_base)
    incomes.add(_additional_medicare_threshold(federal, payroll))
    return {_money(income) for income in incomes}


def _additional_medicare_threshold(
    federal: FederalTaxParameters, payroll: PayrollTaxParameters
) -> Decimal:
    return payroll.additional_medicare_thresholds.get(
        federal.filing_status, payroll.additional_medicare_threshold_single
    )


def _rate(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0.0000")
    return (numerator / denominator).quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)
