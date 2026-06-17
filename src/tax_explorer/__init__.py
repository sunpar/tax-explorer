from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from itertools import pairwise
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


def _finite_decimal(value: Decimal | int | float | str, field_name: str) -> Decimal:
    try:
        amount = _decimal(value)
    except InvalidOperation:
        raise ValueError(f"{field_name} must be a finite decimal") from None
    if not amount.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    return amount


def _validated_non_negative_money(
    value: Decimal | int | float | str,
    field_name: str,
) -> Decimal:
    amount = _finite_decimal(value, field_name)
    if amount < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return amount.quantize(MONEY, rounding=ROUND_HALF_UP)


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
    dependent_count: int = 0
    secondary_income: Decimal = ZERO_MONEY


@dataclass(frozen=True)
class PayrollBreakdownItem:
    label: str
    gross_income: Decimal
    payroll_wages: Decimal
    employee_social_security_tax: Decimal
    employee_medicare_tax: Decimal
    employee_additional_medicare_tax: Decimal
    total_employee_payroll_tax: Decimal
    employer_social_security_tax: Decimal
    employer_medicare_tax: Decimal
    total_employer_payroll_tax: Decimal
    total_payroll_tax: Decimal


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
    payroll_breakdown: tuple[PayrollBreakdownItem, ...]


@dataclass(frozen=True)
class _PretaxDeductions:
    employee_401k_contribution: Decimal
    health_fsa_contribution: Decimal
    dependent_care_fsa_contribution: Decimal
    total_pretax_deductions: Decimal
    payroll_exclusions_by_worker: tuple[Decimal, ...] = ()


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
    payroll_breakdown: tuple[PayrollBreakdownItem, ...]


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
    dependent_care_fsa_limit=_money("7500"),
    gradual_phase_in_start_rate=Decimal("0.01"),
)


def calculate_tax_burden(
    scenario: TaxScenario,
    federal: FederalTaxParameters = FEDERAL_2026_SINGLE,
    payroll: PayrollTaxParameters = PAYROLL_2026,
    pretax_deductions: PretaxDeductionParameters = PRETAX_DEDUCTIONS_2026,
) -> TaxBurden:
    federal = _validated_tax_parameters(federal, payroll, pretax_deductions)
    return _calculate_tax_burden(
        scenario,
        federal=federal,
        payroll=payroll,
        pretax_deductions=pretax_deductions,
    )


def _calculate_tax_burden(
    scenario: TaxScenario,
    federal: FederalTaxParameters,
    payroll: PayrollTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
) -> TaxBurden:
    gross_income = _validated_non_negative_money(
        scenario.gross_income, "gross_income"
    )
    secondary_income = _validated_non_negative_money(
        scenario.secondary_income, "secondary_income"
    )
    dependent_count = _validate_dependent_count(scenario.dependent_count)
    secondary_income = _validate_secondary_income(
        gross_income,
        secondary_income,
        federal,
    )
    worker_count = _worker_count(federal, secondary_income)
    _validate_pretax_deduction_mode(scenario.pretax_deduction_mode)
    active_pretax_deductions = _active_pretax_deduction_parameters(
        federal, pretax_deductions, dependent_count, worker_count
    )

    amounts = _calculate_tax_amounts(
        gross_income,
        secondary_income=secondary_income,
        include_employer_payroll_tax=scenario.include_employer_payroll_tax,
        pretax_deduction_mode=scenario.pretax_deduction_mode,
        federal=federal,
        payroll=payroll,
        pretax_deductions=active_pretax_deductions,
        worker_count=worker_count,
        rounded=True,
    )
    marginal_employee_tax_rate = _forward_difference_marginal_rate(
        gross_income,
        secondary_income=secondary_income,
        include_employer_payroll_tax=False,
        pretax_deduction_mode=scenario.pretax_deduction_mode,
        federal=federal,
        payroll=payroll,
        pretax_deductions=active_pretax_deductions,
        worker_count=worker_count,
    )
    marginal_tax_rate_with_employer_payroll = _forward_difference_marginal_rate(
        gross_income,
        secondary_income=secondary_income,
        include_employer_payroll_tax=scenario.include_employer_payroll_tax,
        pretax_deduction_mode=scenario.pretax_deduction_mode,
        federal=federal,
        payroll=payroll,
        pretax_deductions=active_pretax_deductions,
        worker_count=worker_count,
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
        payroll_breakdown=amounts.payroll_breakdown,
    )


def build_income_series(
    start: Decimal | int | float | str,
    stop: Decimal | int | float | str,
    step: Decimal | int | float | str,
    include_employer_payroll_tax: bool = False,
    include_marginal_breakpoints: bool = False,
    pretax_deduction_mode: str = PRETAX_DEDUCTION_MODE_MAX_AVAILABLE,
    dependent_count: int = 0,
    secondary_income: Decimal | int | float | str = ZERO_MONEY,
    federal: FederalTaxParameters = FEDERAL_2026_SINGLE,
    payroll: PayrollTaxParameters = PAYROLL_2026,
    pretax_deductions: PretaxDeductionParameters = PRETAX_DEDUCTIONS_2026,
) -> list[TaxBurden]:
    federal = _validated_tax_parameters(federal, payroll, pretax_deductions)
    start_decimal = _finite_decimal(start, "start")
    stop_decimal = _finite_decimal(stop, "stop")
    step_decimal = _finite_decimal(step, "step")
    if step_decimal <= 0:
        raise ValueError("step must be positive")
    if start_decimal < 0 or stop_decimal < 0:
        raise ValueError("income bounds must be non-negative")

    start_amount = _money(start_decimal)
    current = start_amount
    stop_amount = _money(stop_decimal)
    step_amount = _money(step_decimal)
    if step_amount <= 0:
        raise ValueError("step must be positive")
    if current > stop_amount:
        raise ValueError("start must be less than or equal to stop")
    dependent_count = _validate_dependent_count(dependent_count)
    configured_secondary_income = _validate_secondary_income_for_series(
        _validated_non_negative_money(secondary_income, "secondary_income"), federal
    )
    if configured_secondary_income > stop_amount:
        raise ValueError("secondary_income cannot exceed stop")
    worker_count = _worker_count(federal, configured_secondary_income)
    _validate_pretax_deduction_mode(pretax_deduction_mode)
    active_pretax_deductions = _active_pretax_deduction_parameters(
        federal, pretax_deductions, dependent_count, worker_count
    )

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
            active_pretax_deductions,
            pretax_deduction_mode,
            worker_count,
            configured_secondary_income,
        ):
            if start_amount <= income <= stop_amount:
                add_income(income)

    return [
        _calculate_tax_burden(
            TaxScenario(
                gross_income=income,
                include_employer_payroll_tax=include_employer_payroll_tax,
                pretax_deduction_mode=pretax_deduction_mode,
                dependent_count=dependent_count,
                secondary_income=min(configured_secondary_income, income),
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


def _validated_tax_parameters(
    federal: FederalTaxParameters,
    payroll: PayrollTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
) -> FederalTaxParameters:
    federal = _validated_federal_tax_parameters(federal)
    _validate_payroll_tax_parameters(payroll)
    _validate_pretax_deduction_parameters(pretax_deductions)
    return federal


def _validated_federal_tax_parameters(
    federal: FederalTaxParameters,
) -> FederalTaxParameters:
    if not federal.brackets:
        raise ValueError("federal tax brackets are required")
    standard_deduction = _validated_non_negative_money(
        federal.standard_deduction, "standard_deduction"
    )
    brackets = tuple(
        TaxBracket(
            lower_bound=_validated_non_negative_money(
                bracket.lower_bound, "bracket lower_bound"
            ),
            rate=_validated_rate(bracket.rate, "bracket rate"),
        )
        for bracket in federal.brackets
    )

    if brackets[0].lower_bound != ZERO_MONEY:
        raise ValueError("federal tax brackets must start at 0.00")

    for previous_bracket, bracket in pairwise(brackets):
        if bracket.lower_bound <= previous_bracket.lower_bound:
            raise ValueError("federal tax bracket lower_bounds must increase")

    return FederalTaxParameters(
        tax_year=federal.tax_year,
        filing_status=federal.filing_status,
        standard_deduction=standard_deduction,
        brackets=brackets,
    )


def _validate_payroll_tax_parameters(payroll: PayrollTaxParameters) -> None:
    _validated_rate(payroll.social_security_rate, "social_security_rate")
    _validated_non_negative_money(
        payroll.social_security_wage_base,
        "social_security_wage_base",
    )
    _validated_rate(payroll.medicare_rate, "medicare_rate")
    _validated_rate(payroll.additional_medicare_rate, "additional_medicare_rate")
    _validated_non_negative_money(
        payroll.additional_medicare_threshold_single,
        "additional_medicare_threshold_single",
    )
    for threshold in payroll.additional_medicare_thresholds.values():
        _validated_non_negative_money(
            threshold,
            "additional_medicare_threshold",
        )


def _validate_pretax_deduction_parameters(
    parameters: PretaxDeductionParameters,
) -> None:
    _validated_non_negative_money(
        parameters.employee_401k_limit,
        "employee_401k_limit",
    )
    _validated_non_negative_money(parameters.health_fsa_limit, "health_fsa_limit")
    _validated_non_negative_money(
        parameters.dependent_care_fsa_limit,
        "dependent_care_fsa_limit",
    )
    _validated_rate(
        parameters.gradual_phase_in_start_rate,
        "gradual_phase_in_start_rate",
    )


def _validated_rate(value: Decimal | int | float | str, field_name: str) -> Decimal:
    rate = _finite_decimal(value, field_name)
    if rate < 0 or rate > 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return rate


def _validate_dependent_count(dependent_count: int) -> int:
    if dependent_count < 0:
        raise ValueError("dependent_count must be non-negative")
    return dependent_count


def _validate_secondary_income(
    gross_income: Decimal,
    secondary_income: Decimal,
    federal: FederalTaxParameters,
) -> Decimal:
    _validate_secondary_income_for_series(secondary_income, federal)
    if secondary_income > gross_income:
        raise ValueError("secondary_income cannot exceed gross_income")
    return secondary_income


def _validate_secondary_income_for_series(
    secondary_income: Decimal,
    federal: FederalTaxParameters,
) -> Decimal:
    if secondary_income < 0:
        raise ValueError("secondary_income must be non-negative")
    if secondary_income > 0 and federal.filing_status != "married_joint":
        raise ValueError("secondary_income is only supported for married_joint")
    return secondary_income


def _worker_count(
    federal: FederalTaxParameters,
    secondary_income: Decimal,
) -> int:
    return 2 if federal.filing_status == "married_joint" and secondary_income > 0 else 1


def _active_pretax_deduction_parameters(
    federal: FederalTaxParameters,
    parameters: PretaxDeductionParameters,
    dependent_count: int,
    worker_count: int,
) -> PretaxDeductionParameters:
    duplicate_worker_caps = federal.filing_status == "married_joint" and worker_count == 2
    employee_401k_limit = parameters.employee_401k_limit * (
        2 if duplicate_worker_caps else 1
    )
    health_fsa_limit = parameters.health_fsa_limit * (
        2 if duplicate_worker_caps else 1
    )
    if dependent_count <= 0:
        dependent_care_limit = ZERO_MONEY
    elif federal.filing_status == "married_separate":
        dependent_care_limit = _money(parameters.dependent_care_fsa_limit / 2)
    else:
        dependent_care_limit = parameters.dependent_care_fsa_limit

    return PretaxDeductionParameters(
        tax_year=parameters.tax_year,
        employee_401k_limit=employee_401k_limit,
        health_fsa_limit=health_fsa_limit,
        dependent_care_fsa_limit=dependent_care_limit,
        gradual_phase_in_start_rate=parameters.gradual_phase_in_start_rate,
    )


def _calculate_tax_amounts(
    gross_income: Decimal,
    secondary_income: Decimal,
    include_employer_payroll_tax: bool,
    pretax_deduction_mode: str,
    federal: FederalTaxParameters,
    payroll: PayrollTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
    worker_count: int,
    rounded: bool,
) -> _TaxAmounts:
    pretax = _calculate_pretax_deductions(
        gross_income,
        secondary_income=secondary_income,
        federal=federal,
        parameters=pretax_deductions,
        mode=pretax_deduction_mode,
        worker_count=worker_count,
        rounded=rounded,
    )
    taxable_income = max(
        ZERO, gross_income - pretax.total_pretax_deductions - federal.standard_deduction
    )
    federal_income_tax = _calculate_progressive_tax_raw(
        taxable_income, federal.brackets
    )

    worker_incomes = _worker_incomes(gross_income, secondary_income, federal)
    worker_payroll_wages = _worker_payroll_wages(
        gross_income,
        secondary_income,
        federal,
        pretax,
    )
    payroll_wages = sum(worker_payroll_wages, ZERO)
    worker_social_security_tax = tuple(
        min(wages, payroll.social_security_wage_base) * payroll.social_security_rate
        for wages in worker_payroll_wages
    )
    worker_medicare_tax = tuple(
        wages * payroll.medicare_rate for wages in worker_payroll_wages
    )
    employee_social_security_tax = sum(worker_social_security_tax, ZERO)
    employee_medicare_tax = sum(worker_medicare_tax, ZERO)
    additional_medicare_threshold = _additional_medicare_threshold(federal, payroll)
    additional_medicare_wages = max(
        ZERO, payroll_wages - additional_medicare_threshold
    )
    employee_additional_medicare_tax = (
        additional_medicare_wages * payroll.additional_medicare_rate
    )
    worker_additional_medicare_tax = _allocate_amount_by_weight(
        employee_additional_medicare_tax,
        worker_payroll_wages,
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
            payroll_exclusions_by_worker=_round_values_to_total(
                pretax.payroll_exclusions_by_worker,
                _money(
                    pretax.health_fsa_contribution
                    + pretax.dependent_care_fsa_contribution
                ),
            ),
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

    payroll_breakdown = _build_payroll_breakdown(
        worker_incomes=worker_incomes,
        worker_payroll_wages=worker_payroll_wages,
        worker_social_security_tax=worker_social_security_tax,
        worker_medicare_tax=worker_medicare_tax,
        worker_additional_medicare_tax=worker_additional_medicare_tax,
        gross_income=gross_income,
        payroll_wages=payroll_wages,
        employee_social_security_tax=employee_social_security_tax,
        employee_medicare_tax=employee_medicare_tax,
        employee_additional_medicare_tax=employee_additional_medicare_tax,
        total_employee_payroll_tax=total_employee_payroll_tax,
        employer_social_security_tax=employer_social_security_tax,
        employer_medicare_tax=employer_medicare_tax,
        total_employer_payroll_tax=total_employer_payroll_tax,
        include_employer_payroll_tax=include_employer_payroll_tax,
        rounded=rounded,
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
        payroll_breakdown=payroll_breakdown,
    )


def _allocate_amount_by_weight(
    amount: Decimal,
    weights: tuple[Decimal, ...],
) -> tuple[Decimal, ...]:
    if not weights:
        return ()
    total_weight = sum(weights, ZERO)
    if amount <= 0 or total_weight <= 0:
        return tuple(ZERO for _ in weights)

    allocations = []
    remaining_amount = amount
    for index, weight in enumerate(weights):
        if index == len(weights) - 1:
            allocation = remaining_amount
        else:
            allocation = amount * weight / total_weight
            remaining_amount -= allocation
        allocations.append(allocation)

    return tuple(allocations)


def _round_values_to_total(
    values: tuple[Decimal, ...],
    rounded_total: Decimal,
) -> tuple[Decimal, ...]:
    if not values:
        return ()

    rounded_values = [_money(value) for value in values]
    residual = rounded_total - sum(rounded_values, ZERO)
    if residual:
        rounded_values[-1] = _money(rounded_values[-1] + residual)

    return tuple(rounded_values)


def _build_payroll_breakdown(
    worker_incomes: tuple[Decimal, ...],
    worker_payroll_wages: tuple[Decimal, ...],
    worker_social_security_tax: tuple[Decimal, ...],
    worker_medicare_tax: tuple[Decimal, ...],
    worker_additional_medicare_tax: tuple[Decimal, ...],
    gross_income: Decimal,
    payroll_wages: Decimal,
    employee_social_security_tax: Decimal,
    employee_medicare_tax: Decimal,
    employee_additional_medicare_tax: Decimal,
    total_employee_payroll_tax: Decimal,
    employer_social_security_tax: Decimal,
    employer_medicare_tax: Decimal,
    total_employer_payroll_tax: Decimal,
    include_employer_payroll_tax: bool,
    rounded: bool,
) -> tuple[PayrollBreakdownItem, ...]:
    if rounded:
        worker_incomes = _round_values_to_total(worker_incomes, _money(gross_income))
        worker_payroll_wages = _round_values_to_total(
            worker_payroll_wages, _money(payroll_wages)
        )
        worker_social_security_tax = _round_values_to_total(
            worker_social_security_tax, employee_social_security_tax
        )
        worker_medicare_tax = _round_values_to_total(
            worker_medicare_tax, employee_medicare_tax
        )
        worker_additional_medicare_tax = _round_values_to_total(
            worker_additional_medicare_tax, employee_additional_medicare_tax
        )

    zero_worker_tax = tuple(ZERO for _ in worker_incomes)
    worker_employer_social_security_tax = (
        worker_social_security_tax if include_employer_payroll_tax else zero_worker_tax
    )
    worker_employer_medicare_tax = (
        worker_medicare_tax if include_employer_payroll_tax else zero_worker_tax
    )
    if rounded:
        worker_employer_social_security_tax = _round_values_to_total(
            worker_employer_social_security_tax, employer_social_security_tax
        )
        worker_employer_medicare_tax = _round_values_to_total(
            worker_employer_medicare_tax, employer_medicare_tax
        )

    worker_rows = []
    label_prefix = "Income" if len(worker_incomes) == 1 else "Income "
    for index, income in enumerate(worker_incomes, start=1):
        employee_payroll_tax = (
            worker_social_security_tax[index - 1]
            + worker_medicare_tax[index - 1]
            + worker_additional_medicare_tax[index - 1]
        )
        employer_payroll_tax = (
            worker_employer_social_security_tax[index - 1]
            + worker_employer_medicare_tax[index - 1]
        )
        if rounded:
            employee_payroll_tax = _money(employee_payroll_tax)
            employer_payroll_tax = _money(employer_payroll_tax)
        worker_rows.append(
            PayrollBreakdownItem(
                label=label_prefix if len(worker_incomes) == 1 else f"Income {index}",
                gross_income=income,
                payroll_wages=worker_payroll_wages[index - 1],
                employee_social_security_tax=worker_social_security_tax[index - 1],
                employee_medicare_tax=worker_medicare_tax[index - 1],
                employee_additional_medicare_tax=worker_additional_medicare_tax[
                    index - 1
                ],
                total_employee_payroll_tax=employee_payroll_tax,
                employer_social_security_tax=worker_employer_social_security_tax[
                    index - 1
                ],
                employer_medicare_tax=worker_employer_medicare_tax[index - 1],
                total_employer_payroll_tax=employer_payroll_tax,
                total_payroll_tax=employee_payroll_tax + employer_payroll_tax,
            )
        )

    total_payroll_tax = total_employee_payroll_tax + total_employer_payroll_tax
    if rounded:
        gross_income = _money(gross_income)
        payroll_wages = _money(payroll_wages)
        total_payroll_tax = _money(total_payroll_tax)

    return tuple(worker_rows) + (
        PayrollBreakdownItem(
            label="Total",
            gross_income=gross_income,
            payroll_wages=payroll_wages,
            employee_social_security_tax=employee_social_security_tax,
            employee_medicare_tax=employee_medicare_tax,
            employee_additional_medicare_tax=employee_additional_medicare_tax,
            total_employee_payroll_tax=total_employee_payroll_tax,
            employer_social_security_tax=employer_social_security_tax,
            employer_medicare_tax=employer_medicare_tax,
            total_employer_payroll_tax=total_employer_payroll_tax,
            total_payroll_tax=total_payroll_tax,
        ),
    )


def _calculate_pretax_deductions(
    gross_income: Decimal,
    secondary_income: Decimal,
    federal: FederalTaxParameters,
    parameters: PretaxDeductionParameters,
    mode: str,
    worker_count: int,
    rounded: bool,
) -> _PretaxDeductions:
    total_cap = _pretax_deduction_cap(parameters)
    if total_cap <= 0:
        return _PretaxDeductions(
            ZERO,
            ZERO,
            ZERO,
            ZERO,
            tuple(ZERO for _ in range(worker_count)),
        )

    if mode == PRETAX_DEDUCTION_MODE_MAX_AVAILABLE:
        requested_deduction = min(gross_income, total_cap)
    elif gross_income <= federal.standard_deduction:
        requested_deduction = ZERO
    else:
        phase_start = federal.standard_deduction
        phase_end = _gradual_phase_in_end_income(federal, parameters, worker_count)
        z = max(
            ZERO,
            min(Decimal("1"), (gross_income - phase_start) / (phase_end - phase_start)),
        )
        end_rate = total_cap / phase_end
        deduction_rate = (
            parameters.gradual_phase_in_start_rate
            + (end_rate - parameters.gradual_phase_in_start_rate) * z
        )
        requested_deduction = min(total_cap, gross_income * deduction_rate)

    worker_incomes = _worker_incomes(gross_income, secondary_income, federal)
    non_dependent_cap = parameters.employee_401k_limit + parameters.health_fsa_limit
    requested_non_dependent = (
        requested_deduction * non_dependent_cap / total_cap
        if non_dependent_cap > 0
        else ZERO
    )
    worker_non_dependent = _worker_non_dependent_pretax_deductions(
        requested_non_dependent,
        worker_incomes,
        parameters,
    )
    employee_401k = sum(
        (deduction.employee_401k_contribution for deduction in worker_non_dependent),
        ZERO,
    )
    health_fsa = sum(
        (deduction.health_fsa_contribution for deduction in worker_non_dependent),
        ZERO,
    )
    worker_non_dependent_totals = tuple(
        deduction.total_pretax_deductions for deduction in worker_non_dependent
    )

    requested_dependent_care = (
        requested_deduction * parameters.dependent_care_fsa_limit / total_cap
        if parameters.dependent_care_fsa_limit > 0
        else ZERO
    )
    dependent_care_by_worker = _worker_dependent_care_deductions(
        requested_dependent_care,
        worker_incomes,
        worker_non_dependent_totals,
        parameters,
    )
    dependent_care = sum(dependent_care_by_worker, ZERO)
    total_deduction = employee_401k + health_fsa + dependent_care
    payroll_exclusions_by_worker = tuple(
        worker_non_dependent[index].health_fsa_contribution
        + dependent_care_by_worker[index]
        for index in range(len(worker_incomes))
    )

    if rounded:
        total_deduction = _money(total_deduction)
        employee_401k = _money(employee_401k)
        health_fsa = _money(health_fsa)
        dependent_care = _money(total_deduction - employee_401k - health_fsa)
        payroll_exclusions_by_worker = _round_values_to_total(
            payroll_exclusions_by_worker,
            _money(health_fsa + dependent_care),
        )

    return _PretaxDeductions(
        employee_401k_contribution=employee_401k,
        health_fsa_contribution=health_fsa,
        dependent_care_fsa_contribution=dependent_care,
        total_pretax_deductions=total_deduction,
        payroll_exclusions_by_worker=payroll_exclusions_by_worker,
    )


def _worker_non_dependent_pretax_deductions(
    requested_deduction: Decimal,
    worker_incomes: tuple[Decimal, ...],
    parameters: PretaxDeductionParameters,
) -> tuple[_PretaxDeductions, ...]:
    worker_count = len(worker_incomes)
    worker_401k_cap = parameters.employee_401k_limit / worker_count
    worker_health_fsa_cap = parameters.health_fsa_limit / worker_count
    worker_total_cap = worker_401k_cap + worker_health_fsa_cap
    if requested_deduction <= 0 or worker_total_cap <= 0:
        return tuple(
            _PretaxDeductions(ZERO, ZERO, ZERO, ZERO, (ZERO,))
            for _ in worker_incomes
        )

    worker_capacities = tuple(
        max(ZERO, min(income, worker_total_cap)) for income in worker_incomes
    )
    deduction = min(requested_deduction, sum(worker_capacities, ZERO))
    worker_totals = _allocate_amount_by_weight(deduction, worker_capacities)

    allocations = []
    for worker_total in worker_totals:
        employee_401k = worker_total * worker_401k_cap / worker_total_cap
        health_fsa = worker_total - employee_401k
        allocations.append(
            _PretaxDeductions(
                employee_401k_contribution=employee_401k,
                health_fsa_contribution=health_fsa,
                dependent_care_fsa_contribution=ZERO,
                total_pretax_deductions=worker_total,
                payroll_exclusions_by_worker=(health_fsa,),
            )
        )

    return tuple(allocations)


def _worker_dependent_care_deductions(
    requested_deduction: Decimal,
    worker_incomes: tuple[Decimal, ...],
    worker_non_dependent_totals: tuple[Decimal, ...],
    parameters: PretaxDeductionParameters,
) -> tuple[Decimal, ...]:
    if requested_deduction <= 0 or parameters.dependent_care_fsa_limit <= 0:
        return tuple(ZERO for _ in worker_incomes)

    capacities = tuple(
        max(ZERO, income - worker_non_dependent_totals[index])
        for index, income in enumerate(worker_incomes)
    )
    deduction = min(
        requested_deduction,
        parameters.dependent_care_fsa_limit,
        sum(capacities, ZERO),
    )
    return _allocate_amount_by_weight(deduction, capacities)


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
    federal: FederalTaxParameters,
    parameters: PretaxDeductionParameters,
    worker_count: int,
) -> Decimal:
    if worker_count > 1:
        single_worker_cap = (
            parameters.employee_401k_limit / worker_count
            + parameters.health_fsa_limit / worker_count
            + parameters.dependent_care_fsa_limit
        )
        single_worker_end = (
            federal.standard_deduction
            + _next_to_last_bracket_start(federal)
            + single_worker_cap
        )
        return _money(single_worker_end * Decimal("1.5"))

    return (
        federal.standard_deduction
        + _next_to_last_bracket_start(federal)
        + _pretax_deduction_cap(parameters)
    )


def _forward_difference_marginal_rate(
    gross_income: Decimal,
    secondary_income: Decimal,
    include_employer_payroll_tax: bool,
    pretax_deduction_mode: str,
    federal: FederalTaxParameters,
    payroll: PayrollTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
    worker_count: int,
) -> Decimal:
    current = _calculate_tax_amounts(
        gross_income,
        secondary_income=secondary_income,
        include_employer_payroll_tax=include_employer_payroll_tax,
        pretax_deduction_mode=pretax_deduction_mode,
        federal=federal,
        payroll=payroll,
        pretax_deductions=pretax_deductions,
        worker_count=worker_count,
        rounded=False,
    )
    next_amounts = _calculate_tax_amounts(
        gross_income + ONE_DOLLAR,
        secondary_income=secondary_income,
        include_employer_payroll_tax=include_employer_payroll_tax,
        pretax_deduction_mode=pretax_deduction_mode,
        federal=federal,
        payroll=payroll,
        pretax_deductions=pretax_deductions,
        worker_count=worker_count,
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


def _marginal_rate_change_incomes(
    federal: FederalTaxParameters,
    payroll: PayrollTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
    pretax_deduction_mode: str,
    worker_count: int,
    secondary_income: Decimal,
) -> set[Decimal]:
    incomes: set[Decimal] = set()
    if pretax_deduction_mode == PRETAX_DEDUCTION_MODE_MAX_AVAILABLE:
        incomes.update(
            _max_available_pretax_deduction_change_incomes(
                federal,
                pretax_deductions,
                worker_count,
                secondary_income,
            )
        )
        for bracket in federal.brackets:
            income = _solve_income_for_target(
                target=federal.standard_deduction + bracket.lower_bound,
                value_at_income=lambda gross_income: _income_after_pretax_before_tax(
                    gross_income,
                    min(secondary_income, gross_income),
                    federal,
                    pretax_deductions,
                    pretax_deduction_mode,
                    worker_count,
                ),
            )
            if income is not None:
                incomes.add(income)
    else:
        incomes.add(federal.standard_deduction)
        incomes.add(
            _gradual_phase_in_end_income(federal, pretax_deductions, worker_count)
        )
        for bracket in federal.brackets[1:]:
            income = _solve_income_for_target(
                target=bracket.lower_bound,
                value_at_income=lambda gross_income: _taxable_income_before_tax(
                    gross_income,
                    min(secondary_income, gross_income),
                    federal,
                    pretax_deductions,
                    pretax_deduction_mode,
                    worker_count,
                ),
            )
            if income is not None:
                incomes.add(income)

    for worker_index in range(worker_count):
        income = _solve_income_for_target(
            target=payroll.social_security_wage_base,
            value_at_income=lambda gross_income, index=worker_index: (
                _worker_payroll_wages_before_tax(
                    gross_income,
                    min(secondary_income, gross_income),
                    federal,
                    pretax_deductions,
                    pretax_deduction_mode,
                    worker_count,
                )[index]
            ),
        )
        if income is not None:
            incomes.add(income)

    additional_medicare_income = _solve_income_for_target(
        target=_additional_medicare_threshold(federal, payroll),
        value_at_income=lambda gross_income: _payroll_wages(
            gross_income,
            min(secondary_income, gross_income),
            federal,
            pretax_deductions,
            pretax_deduction_mode,
            worker_count,
        ),
    )
    if additional_medicare_income is not None:
        incomes.add(additional_medicare_income)

    return {_money(income) for income in incomes}


def _max_available_pretax_deduction_change_incomes(
    federal: FederalTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
    worker_count: int,
    secondary_income: Decimal,
) -> set[Decimal]:
    incomes: set[Decimal] = set()
    total_cap = _pretax_deduction_cap(pretax_deductions)
    if total_cap <= 0:
        return incomes

    probe_income = max(
        total_cap * Decimal("4") + secondary_income + federal.standard_deduction,
        ONE_DOLLAR,
    )
    max_deduction_income = _solve_income_for_target(
        target=_total_pretax_deductions_before_tax(
            probe_income,
            secondary_income,
            federal,
            pretax_deductions,
            PRETAX_DEDUCTION_MODE_MAX_AVAILABLE,
            worker_count,
        ),
        value_at_income=lambda gross_income: _total_pretax_deductions_before_tax(
            gross_income,
            min(secondary_income, gross_income),
            federal,
            pretax_deductions,
            PRETAX_DEDUCTION_MODE_MAX_AVAILABLE,
            worker_count,
        ),
    )
    if max_deduction_income is not None:
        incomes.add(max_deduction_income)

    non_dependent_cap = (
        pretax_deductions.employee_401k_limit + pretax_deductions.health_fsa_limit
    )
    if worker_count > 1 and non_dependent_cap > 0:
        per_worker_cap = non_dependent_cap / worker_count
        if secondary_income > per_worker_cap:
            incomes.add(per_worker_cap)
            incomes.add(secondary_income)
            incomes.add(secondary_income + per_worker_cap)

    return incomes


def _income_after_pretax_before_tax(
    gross_income: Decimal,
    secondary_income: Decimal,
    federal: FederalTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
    pretax_deduction_mode: str,
    worker_count: int,
) -> Decimal:
    pretax = _calculate_pretax_deductions(
        gross_income,
        secondary_income=secondary_income,
        federal=federal,
        parameters=pretax_deductions,
        mode=pretax_deduction_mode,
        worker_count=worker_count,
        rounded=False,
    )
    return max(ZERO, gross_income - pretax.total_pretax_deductions)


def _total_pretax_deductions_before_tax(
    gross_income: Decimal,
    secondary_income: Decimal,
    federal: FederalTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
    pretax_deduction_mode: str,
    worker_count: int,
) -> Decimal:
    return _calculate_pretax_deductions(
        gross_income,
        secondary_income=secondary_income,
        federal=federal,
        parameters=pretax_deductions,
        mode=pretax_deduction_mode,
        worker_count=worker_count,
        rounded=False,
    ).total_pretax_deductions


def _taxable_income_before_tax(
    gross_income: Decimal,
    secondary_income: Decimal,
    federal: FederalTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
    pretax_deduction_mode: str,
    worker_count: int,
) -> Decimal:
    pretax = _calculate_pretax_deductions(
        gross_income,
        secondary_income=secondary_income,
        federal=federal,
        parameters=pretax_deductions,
        mode=pretax_deduction_mode,
        worker_count=worker_count,
        rounded=False,
    )
    return max(
        ZERO,
        gross_income - pretax.total_pretax_deductions - federal.standard_deduction,
    )


def _payroll_wages(
    gross_income: Decimal,
    secondary_income: Decimal,
    federal: FederalTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
    pretax_deduction_mode: str,
    worker_count: int,
) -> Decimal:
    return sum(
        _worker_payroll_wages_before_tax(
            gross_income,
            secondary_income,
            federal,
            pretax_deductions,
            pretax_deduction_mode,
            worker_count,
        ),
        ZERO,
    )


def _worker_payroll_wages_before_tax(
    gross_income: Decimal,
    secondary_income: Decimal,
    federal: FederalTaxParameters,
    pretax_deductions: PretaxDeductionParameters,
    pretax_deduction_mode: str,
    worker_count: int,
) -> tuple[Decimal, ...]:
    pretax = _calculate_pretax_deductions(
        gross_income,
        secondary_income=secondary_income,
        federal=federal,
        parameters=pretax_deductions,
        mode=pretax_deduction_mode,
        worker_count=worker_count,
        rounded=False,
    )
    return _worker_payroll_wages(gross_income, secondary_income, federal, pretax)


def _worker_payroll_wages(
    gross_income: Decimal,
    secondary_income: Decimal,
    federal: FederalTaxParameters,
    pretax: _PretaxDeductions,
) -> tuple[Decimal, ...]:
    worker_incomes = _worker_incomes(gross_income, secondary_income, federal)
    if not pretax.payroll_exclusions_by_worker:
        return tuple(max(ZERO, income) for income in worker_incomes)

    return tuple(
        max(ZERO, income - pretax.payroll_exclusions_by_worker[index])
        for index, income in enumerate(worker_incomes)
    )


def _worker_incomes(
    gross_income: Decimal,
    secondary_income: Decimal,
    federal: FederalTaxParameters,
) -> tuple[Decimal, ...]:
    if _worker_count(federal, secondary_income) == 1:
        return (gross_income,)
    secondary = min(secondary_income, gross_income)
    return (gross_income - secondary, secondary)


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
