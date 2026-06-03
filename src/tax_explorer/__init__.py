from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Iterable, Mapping


MONEY = Decimal("0.01")
RATE_PRECISION = Decimal("0.0001")
MAX_INCOME_SERIES_ROWS = 2001
ZERO = Decimal("0")
ZERO_MONEY = Decimal("0.00")
ZERO_RATE = Decimal("0.0000")
ONE_DOLLAR = Decimal("1.00")
PRETAX_DEDUCTION_MODE_MAX_AVAILABLE = "max_available"
PRETAX_DEDUCTION_MODE_GRADUAL_PHASE_IN = "gradual_phase_in"
PRETAX_DEDUCTION_MODE_CHOICES = (
    PRETAX_DEDUCTION_MODE_MAX_AVAILABLE,
    PRETAX_DEDUCTION_MODE_GRADUAL_PHASE_IN,
)
PRETAX_DEDUCTION_MODES = set(PRETAX_DEDUCTION_MODE_CHOICES)


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
class PretaxDeductionParameters:
    tax_year: int
    employee_401k_limit: Decimal
    health_fsa_limit: Decimal
    dependent_care_fsa_limit: Decimal
    gradual_phase_in_start_rate: Decimal


@dataclass(frozen=True)
class TaxScenario:
    gross_income: Decimal
    include_employer_payroll_tax: bool = False
    pretax_deduction_mode: str = PRETAX_DEDUCTION_MODE_MAX_AVAILABLE


@dataclass(frozen=True)
class TaxBurden:
    gross_income: Decimal
    employee_401k_contribution: Decimal
    health_fsa_contribution: Decimal
    dependent_care_fsa_contribution: Decimal
    total_pretax_deductions: Decimal
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


@dataclass(frozen=True)
class _PretaxDeductions:
    employee_401k_contribution: Decimal
    health_fsa_contribution: Decimal
    dependent_care_fsa_contribution: Decimal
    total_pretax_deductions: Decimal


@dataclass(frozen=True)
class _TaxAmounts:
    gross_income: Decimal
    employee_401k_contribution: Decimal
    health_fsa_contribution: Decimal
    dependent_care_fsa_contribution: Decimal
    total_pretax_deductions: Decimal
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
    additional_medicare_thresholds={
        "single": _money("200000"),
        "married_joint": _money("250000"),
        "married_separate": _money("125000"),
        "head_of_household": _money("200000"),
    },
)


PRETAX_DEDUCTIONS_2026 = PretaxDeductionParameters(
    tax_year=2026,
    employee_401k_limit=_money("24500"),
    health_fsa_limit=_money("3400"),
    dependent_care_fsa_limit=ZERO_MONEY,
    gradual_phase_in_start_rate=Decimal("0.01"),
)


def calculate_tax_burden(
    scenario: TaxScenario,
    federal: FederalTaxParameters = FEDERAL_2026_SINGLE,
    payroll: PayrollTaxParameters = PAYROLL_2026,
    pretax_deductions: PretaxDeductionParameters = PRETAX_DEDUCTIONS_2026,
) -> TaxBurden:
    gross_income = _money(scenario.gross_income)
    if gross_income < 0:
        raise ValueError("gross_income must be non-negative")
    _validate_pretax_deduction_mode(scenario.pretax_deduction_mode)

    amounts = _calculate_tax_amounts(
        gross_income,
        include_employer_payroll_tax=scenario.include_employer_payroll_tax,
        pretax_deduction_mode=scenario.pretax_deduction_mode,
        federal=federal,
        payroll=payroll,
        pretax_deductions=pretax_deductions,
        rounded=True,
    )
    marginal_employee_tax_rate = _forward_difference_marginal_rate(
        gross_income,
        include_employer_payroll_tax=False,
        pretax_deduction_mode=scenario.pretax_deduction_mode,
        federal=federal,
        payroll=payroll,
        pretax_deductions=pretax_deductions,
    )
    marginal_tax_rate_with_employer_payroll = _forward_difference_marginal_rate(
        gross_income,
        include_employer_payroll_tax=scenario.include_employer_payroll_tax,
        pretax_deduction_mode=scenario.pretax_deduction_mode,
        federal=federal,
        payroll=payroll,
        pretax_deductions=pretax_deductions,
    )

    return TaxBurden(
        gross_income=gross_income,
        employee_401k_contribution=amounts.employee_401k_contribution,
        health_fsa_contribution=amounts.health_fsa_contribution,
        dependent_care_fsa_contribution=amounts.dependent_care_fsa_contribution,
        total_pretax_deductions=amounts.total_pretax_deductions,
        taxable_income=amounts.taxable_income,
        federal_income_tax=amounts.federal_income_tax,
        employee_social_security_tax=amounts.employee_social_security_tax,
        employee_medicare_tax=amounts.employee_medicare_tax,
        employee_additional_medicare_tax=amounts.employee_additional_medicare_tax,
        total_employee_payroll_tax=amounts.total_employee_payroll_tax,
        total_employee_tax=amounts.total_employee_tax,
        effective_employee_tax_rate=amounts.effective_employee_tax_rate,
        marginal_employee_tax_rate=marginal_employee_tax_rate,
        employer_social_security_tax=amounts.employer_social_security_tax,
        employer_medicare_tax=amounts.employer_medicare_tax,
        total_employer_payroll_tax=amounts.total_employer_payroll_tax,
        total_tax_with_employer_payroll=amounts.total_tax_with_employer_payroll,
        marginal_tax_rate_with_employer_payroll=marginal_tax_rate_with_employer_payroll,
    )


def build_income_series(
    start: Decimal | int | float | str,
    stop: Decimal | int | float | str,
    step: Decimal | int | float | str,
    include_employer_payroll_tax: bool = False,
    include_marginal_breakpoints: bool = False,
    pretax_deduction_mode: str = PRETAX_DEDUCTION_MODE_MAX_AVAILABLE,
    federal: FederalTaxParameters = FEDERAL_2026_SINGLE,
    payroll: PayrollTaxParameters = PAYROLL_2026,
    pretax_deductions: PretaxDeductionParameters = PRETAX_DEDUCTIONS_2026,
) -> list[TaxBurden]:
    current = _money(start)
    start_amount = current
    stop_amount = _money(stop)
    step_amount = _money(step)
    if step_amount <= 0:
        raise ValueError("step must be positive")
    if current < 0 or stop_amount < 0:
        raise ValueError("income bounds must be non-negative")
    if current > stop_amount:
        raise ValueError("start must be less than or equal to stop")
    _validate_pretax_deduction_mode(pretax_deduction_mode)

    incomes: set[Decimal] = set()

    def add_income(income: Decimal) -> None:
        incomes.add(income)
        if len(incomes) > MAX_INCOME_SERIES_ROWS:
            raise ValueError(
                f"income-series supports at most {MAX_INCOME_SERIES_ROWS} rows"
            )

    while current <= stop_amount:
        add_income(current)
        current = _money(current + step_amount)

    if include_marginal_breakpoints:
        add_income(stop_amount)
        for income in _marginal_rate_change_incomes(
            federal,
            payroll,
            pretax_deductions,
            pretax_deduction_mode,
        ):
            if start_amount <= income <= stop_amount:
                add_income(income)

    return [
        calculate_tax_burden(
            TaxScenario(
                gross_income=income,
                include_employer_payroll_tax=include_employer_payroll_tax,
                pretax_deduction_mode=pretax_deduction_mode,
            ),
            federal=federal,
            payroll=payroll,
            pretax_deductions=pretax_deductions,
        )
        for income in sorted(incomes)
    ]


def _validate_pretax_deduction_mode(mode: str) -> None:
    if mode not in PRETAX_DEDUCTION_MODES:
        raise ValueError(f"unknown pretax_deduction_mode: {mode}")


def _calculate_tax_amounts(
    gross_income: Decimal,
    include_employer_payroll_tax: bool,
    pretax_deduction_mode: str,
    federal: FederalTaxParameters,
    payroll: PayrollTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
    rounded: bool,
) -> _TaxAmounts:
    pretax = _calculate_pretax_deductions(
        gross_income,
        federal=federal,
        parameters=pretax_deductions,
        mode=pretax_deduction_mode,
        rounded=rounded,
    )
    taxable_income = max(
        ZERO, gross_income - pretax.total_pretax_deductions - federal.standard_deduction
    )
    federal_income_tax = _calculate_progressive_tax_raw(
        taxable_income, federal.brackets
    )

    payroll_wages = max(ZERO, gross_income - pretax.health_fsa_contribution)
    social_security_wages = min(payroll_wages, payroll.social_security_wage_base)
    employee_social_security_tax = social_security_wages * payroll.social_security_rate
    employee_medicare_tax = payroll_wages * payroll.medicare_rate
    additional_medicare_threshold = _additional_medicare_threshold(federal, payroll)
    additional_medicare_wages = max(
        ZERO, payroll_wages - additional_medicare_threshold
    )
    employee_additional_medicare_tax = (
        additional_medicare_wages * payroll.additional_medicare_rate
    )
    total_employee_payroll_tax = (
        employee_social_security_tax
        + employee_medicare_tax
        + employee_additional_medicare_tax
    )
    total_employee_tax = federal_income_tax + total_employee_payroll_tax

    employer_social_security_tax = ZERO
    employer_medicare_tax = ZERO
    if include_employer_payroll_tax:
        employer_social_security_tax = employee_social_security_tax
        employer_medicare_tax = employee_medicare_tax

    total_employer_payroll_tax = (
        employer_social_security_tax + employer_medicare_tax
    )
    total_tax_with_employer_payroll = (
        total_employee_tax + total_employer_payroll_tax
    )

    if rounded:
        pretax = _PretaxDeductions(
            employee_401k_contribution=_money(pretax.employee_401k_contribution),
            health_fsa_contribution=_money(pretax.health_fsa_contribution),
            dependent_care_fsa_contribution=_money(
                pretax.dependent_care_fsa_contribution
            ),
            total_pretax_deductions=_money(pretax.total_pretax_deductions),
        )
        taxable_income = _money(taxable_income)
        federal_income_tax = _money(federal_income_tax)
        employee_social_security_tax = _money(employee_social_security_tax)
        employee_medicare_tax = _money(employee_medicare_tax)
        employee_additional_medicare_tax = _money(employee_additional_medicare_tax)
        total_employee_payroll_tax = _money(
            employee_social_security_tax
            + employee_medicare_tax
            + employee_additional_medicare_tax
        )
        total_employee_tax = _money(federal_income_tax + total_employee_payroll_tax)
        employer_social_security_tax = _money(employer_social_security_tax)
        employer_medicare_tax = _money(employer_medicare_tax)
        total_employer_payroll_tax = _money(
            employer_social_security_tax + employer_medicare_tax
        )
        total_tax_with_employer_payroll = _money(
            total_employee_tax + total_employer_payroll_tax
        )

    return _TaxAmounts(
        gross_income=gross_income,
        employee_401k_contribution=pretax.employee_401k_contribution,
        health_fsa_contribution=pretax.health_fsa_contribution,
        dependent_care_fsa_contribution=pretax.dependent_care_fsa_contribution,
        total_pretax_deductions=pretax.total_pretax_deductions,
        taxable_income=taxable_income,
        federal_income_tax=federal_income_tax,
        employee_social_security_tax=employee_social_security_tax,
        employee_medicare_tax=employee_medicare_tax,
        employee_additional_medicare_tax=employee_additional_medicare_tax,
        total_employee_payroll_tax=total_employee_payroll_tax,
        total_employee_tax=total_employee_tax,
        effective_employee_tax_rate=_rate(total_employee_tax, gross_income),
        employer_social_security_tax=employer_social_security_tax,
        employer_medicare_tax=employer_medicare_tax,
        total_employer_payroll_tax=total_employer_payroll_tax,
        total_tax_with_employer_payroll=total_tax_with_employer_payroll,
    )


def _calculate_pretax_deductions(
    gross_income: Decimal,
    federal: FederalTaxParameters,
    parameters: PretaxDeductionParameters,
    mode: str,
    rounded: bool,
) -> _PretaxDeductions:
    total_cap = _pretax_deduction_cap(parameters)
    if total_cap <= 0:
        return _PretaxDeductions(ZERO, ZERO, ZERO, ZERO)

    if mode == PRETAX_DEDUCTION_MODE_MAX_AVAILABLE:
        total_deduction = min(gross_income, total_cap)
    elif gross_income <= federal.standard_deduction:
        total_deduction = ZERO
    else:
        phase_start = federal.standard_deduction
        phase_end = _gradual_phase_in_end_income(federal, parameters)
        z = max(
            ZERO,
            min(Decimal("1"), (gross_income - phase_start) / (phase_end - phase_start)),
        )
        end_rate = total_cap / phase_end
        deduction_rate = (
            parameters.gradual_phase_in_start_rate
            + (end_rate - parameters.gradual_phase_in_start_rate) * z
        )
        total_deduction = min(total_cap, gross_income * deduction_rate)

    if rounded:
        total_deduction = _money(total_deduction)
        employee_401k = _money(
            total_deduction * parameters.employee_401k_limit / total_cap
        )
        dependent_care = _money(
            total_deduction * parameters.dependent_care_fsa_limit / total_cap
        )
        health_fsa = _money(total_deduction - employee_401k - dependent_care)
    else:
        employee_401k = total_deduction * parameters.employee_401k_limit / total_cap
        health_fsa = total_deduction * parameters.health_fsa_limit / total_cap
        dependent_care = (
            total_deduction * parameters.dependent_care_fsa_limit / total_cap
        )

    return _PretaxDeductions(
        employee_401k_contribution=employee_401k,
        health_fsa_contribution=health_fsa,
        dependent_care_fsa_contribution=dependent_care,
        total_pretax_deductions=total_deduction,
    )


def _next_to_last_bracket_start(federal: FederalTaxParameters) -> Decimal:
    if len(federal.brackets) < 2:
        return federal.brackets[-1].lower_bound
    return federal.brackets[-2].lower_bound


def _pretax_deduction_cap(parameters: PretaxDeductionParameters) -> Decimal:
    return (
        parameters.employee_401k_limit
        + parameters.health_fsa_limit
        + parameters.dependent_care_fsa_limit
    )


def _gradual_phase_in_end_income(
    federal: FederalTaxParameters, parameters: PretaxDeductionParameters
) -> Decimal:
    return (
        federal.standard_deduction
        + _next_to_last_bracket_start(federal)
        + _pretax_deduction_cap(parameters)
    )


def _forward_difference_marginal_rate(
    gross_income: Decimal,
    include_employer_payroll_tax: bool,
    pretax_deduction_mode: str,
    federal: FederalTaxParameters,
    payroll: PayrollTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
) -> Decimal:
    current = _calculate_tax_amounts(
        gross_income,
        include_employer_payroll_tax=include_employer_payroll_tax,
        pretax_deduction_mode=pretax_deduction_mode,
        federal=federal,
        payroll=payroll,
        pretax_deductions=pretax_deductions,
        rounded=False,
    )
    next_amounts = _calculate_tax_amounts(
        gross_income + ONE_DOLLAR,
        include_employer_payroll_tax=include_employer_payroll_tax,
        pretax_deduction_mode=pretax_deduction_mode,
        federal=federal,
        payroll=payroll,
        pretax_deductions=pretax_deductions,
        rounded=False,
    )
    current_tax = (
        current.total_tax_with_employer_payroll
        if include_employer_payroll_tax
        else current.total_employee_tax
    )
    next_tax = (
        next_amounts.total_tax_with_employer_payroll
        if include_employer_payroll_tax
        else next_amounts.total_employee_tax
    )
    return ((next_tax - current_tax) / ONE_DOLLAR).quantize(
        RATE_PRECISION, rounding=ROUND_HALF_UP
    )


def _calculate_progressive_tax_raw(
    taxable_income: Decimal, brackets: Iterable[TaxBracket]
) -> Decimal:
    bracket_iter = iter(brackets)
    try:
        bracket = next(bracket_iter)
    except StopIteration:
        return ZERO

    tax = ZERO
    for next_bracket in bracket_iter:
        bracket_ceiling = next_bracket.lower_bound
        taxable_at_rate = max(
            ZERO, min(taxable_income, bracket_ceiling) - bracket.lower_bound
        )
        tax += taxable_at_rate * bracket.rate
        if taxable_income <= bracket_ceiling:
            return tax
        bracket = next_bracket
    else:
        taxable_at_rate = max(ZERO, taxable_income - bracket.lower_bound)
        tax += taxable_at_rate * bracket.rate

    return tax


def _calculate_progressive_tax(
    taxable_income: Decimal, brackets: Iterable[TaxBracket]
) -> Decimal:
    return _money(_calculate_progressive_tax_raw(taxable_income, brackets))


def _marginal_rate_change_incomes(
    federal: FederalTaxParameters,
    payroll: PayrollTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
    pretax_deduction_mode: str,
) -> set[Decimal]:
    total_cap = _pretax_deduction_cap(pretax_deductions)
    incomes: set[Decimal] = set()
    if pretax_deduction_mode == PRETAX_DEDUCTION_MODE_MAX_AVAILABLE:
        if total_cap > 0:
            incomes.add(total_cap)
        taxable_income_start = federal.standard_deduction + total_cap
        incomes.update(
            taxable_income_start + bracket.lower_bound
            for bracket in federal.brackets
        )
    else:
        incomes.add(federal.standard_deduction)
        incomes.add(_gradual_phase_in_end_income(federal, pretax_deductions))
        for bracket in federal.brackets[1:]:
            income = _solve_income_for_target(
                target=bracket.lower_bound,
                value_at_income=lambda gross_income: _taxable_income_before_tax(
                    gross_income,
                    federal,
                    pretax_deductions,
                    pretax_deduction_mode,
                ),
            )
            if income is not None:
                incomes.add(income)

    for payroll_threshold in (
        payroll.social_security_wage_base,
        _additional_medicare_threshold(federal, payroll),
    ):
        income = _solve_income_for_target(
            target=payroll_threshold,
            value_at_income=lambda gross_income: _payroll_wages(
                gross_income,
                federal,
                pretax_deductions,
                pretax_deduction_mode,
            ),
        )
        if income is not None:
            incomes.add(income)

    return {_money(income) for income in incomes}


def _taxable_income_before_tax(
    gross_income: Decimal,
    federal: FederalTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
    pretax_deduction_mode: str,
) -> Decimal:
    pretax = _calculate_pretax_deductions(
        gross_income,
        federal=federal,
        parameters=pretax_deductions,
        mode=pretax_deduction_mode,
        rounded=False,
    )
    return max(
        ZERO,
        gross_income - pretax.total_pretax_deductions - federal.standard_deduction,
    )


def _payroll_wages(
    gross_income: Decimal,
    federal: FederalTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
    pretax_deduction_mode: str,
) -> Decimal:
    pretax = _calculate_pretax_deductions(
        gross_income,
        federal=federal,
        parameters=pretax_deductions,
        mode=pretax_deduction_mode,
        rounded=False,
    )
    return max(ZERO, gross_income - pretax.health_fsa_contribution)


def _solve_income_for_target(
    target: Decimal, value_at_income: Callable[[Decimal], Decimal]
) -> Decimal | None:
    if target < 0:
        return None

    lower = ZERO
    upper = max(ONE_DOLLAR, target)
    while value_at_income(upper) < target:
        upper *= 2
        if upper > Decimal("1000000000"):
            return None

    for _ in range(80):
        midpoint = (lower + upper) / 2
        if value_at_income(midpoint) < target:
            lower = midpoint
        else:
            upper = midpoint

    return _money(upper)


def _additional_medicare_threshold(
    federal: FederalTaxParameters, payroll: PayrollTaxParameters
) -> Decimal:
    return payroll.additional_medicare_thresholds.get(
        federal.filing_status, payroll.additional_medicare_threshold_single
    )


def _rate(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return ZERO_RATE
    return (numerator / denominator).quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)
