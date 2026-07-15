import re
from dataclasses import replace
from decimal import Decimal

import pytest
import tax_explorer as tax_module

from tax_explorer import (
    FEDERAL_2026_SINGLE,
    PAYROLL_2026,
    PRETAX_DEDUCTIONS_2026,
    FederalTaxParameters,
    PayrollTaxParameters,
    TaxBracket,
    TaxScenario,
    build_income_series,
    calculate_tax_burden,
)


def money(value: str) -> Decimal:
    return Decimal(value)


def federal_with_brackets(brackets: tuple[TaxBracket, ...]) -> FederalTaxParameters:
    return FederalTaxParameters(
        tax_year=2026,
        filing_status="single",
        standard_deduction=money("0.00"),
        brackets=brackets,
    )


FEDERAL_2026_MARRIED_JOINT = FederalTaxParameters(
    tax_year=2026,
    filing_status="married_joint",
    standard_deduction=money("32200.00"),
    brackets=(
        TaxBracket(money("0.00"), Decimal("0.10")),
        TaxBracket(money("24800.00"), Decimal("0.12")),
        TaxBracket(money("100800.00"), Decimal("0.22")),
        TaxBracket(money("211400.00"), Decimal("0.24")),
        TaxBracket(money("403550.00"), Decimal("0.32")),
        TaxBracket(money("512450.00"), Decimal("0.35")),
        TaxBracket(money("768700.00"), Decimal("0.37")),
    ),
)


def test_standard_deduction_eliminates_income_tax_below_threshold():
    result = calculate_tax_burden(TaxScenario(gross_income=money("10000")))

    assert result.employee_401k_contribution == money("8781.36")
    assert result.health_fsa_contribution == money("1218.64")
    assert result.dependent_care_fsa_contribution == money("0.00")
    assert result.total_pretax_deductions == money("10000.00")
    assert result.federal_income_tax == money("0.00")
    assert result.employee_social_security_tax == money("544.44")
    assert result.employee_medicare_tax == money("127.33")
    assert result.employee_additional_medicare_tax == money("0.00")
    assert result.total_employee_tax == money("671.77")


def test_federal_income_tax_uses_progressive_2026_single_brackets_after_standard_deduction():
    result = calculate_tax_burden(TaxScenario(gross_income=money("100000")))

    assert FEDERAL_2026_SINGLE.standard_deduction == money("16100.00")
    assert result.employee_401k_contribution == money("24500.00")
    assert result.health_fsa_contribution == money("3400.00")
    assert result.total_pretax_deductions == money("27900.00")
    assert result.taxable_income == money("56000.00")
    assert result.federal_income_tax == money("7032.00")
    assert result.total_employee_tax == money("14421.90")
    assert result.effective_employee_tax_rate == Decimal("0.1442")
    assert result.marginal_employee_tax_rate == Decimal("0.2965")


@pytest.mark.parametrize(
    ("brackets", "message"),
    [
        ((), "federal tax brackets are required"),
        (
            (TaxBracket(money("100.00"), Decimal("0.10")),),
            "federal tax brackets must start at 0.00",
        ),
        (
            (
                TaxBracket(money("0.00"), Decimal("0.10")),
                TaxBracket(money("0.00"), Decimal("0.12")),
            ),
            "federal tax bracket lower_bounds must increase",
        ),
        (
            (
                TaxBracket(money("0.00"), Decimal("0.10")),
                TaxBracket(money("100.00"), Decimal("0.12")),
                TaxBracket(money("50.00"), Decimal("0.22")),
            ),
            "federal tax bracket lower_bounds must increase",
        ),
    ],
)
def test_calculate_tax_burden_rejects_malformed_federal_brackets(
    brackets,
    message,
):
    federal = federal_with_brackets(brackets)

    with pytest.raises(ValueError, match=re.escape(message)):
        calculate_tax_burden(TaxScenario(gross_income=money("1000")), federal=federal)


def test_build_income_series_rejects_malformed_federal_brackets():
    federal = federal_with_brackets(
        (
            TaxBracket(money("0.00"), Decimal("0.10")),
            TaxBracket(money("0.00"), Decimal("0.12")),
        )
    )

    with pytest.raises(
        ValueError,
        match=re.escape("federal tax bracket lower_bounds must increase"),
    ):
        build_income_series(start=0, stop=1000, step=1000, federal=federal)


@pytest.mark.parametrize(
    ("federal", "message"),
    [
        (
            replace(FEDERAL_2026_SINGLE, standard_deduction=Decimal("NaN")),
            "standard_deduction must be a finite decimal",
        ),
        (
            replace(FEDERAL_2026_SINGLE, standard_deduction=Decimal("-1.00")),
            "standard_deduction must be non-negative",
        ),
        (
            federal_with_brackets(
                (
                    TaxBracket(money("0.00"), Decimal("0.10")),
                    TaxBracket(Decimal("NaN"), Decimal("0.12")),
                )
            ),
            "bracket lower_bound must be a finite decimal",
        ),
        (
            federal_with_brackets((TaxBracket(Decimal("-1.00"), Decimal("0.10")),)),
            "bracket lower_bound must be non-negative",
        ),
        (
            federal_with_brackets((TaxBracket(money("0.00"), Decimal("NaN")),)),
            "bracket rate must be a finite decimal",
        ),
        (
            federal_with_brackets((TaxBracket(money("0.00"), Decimal("1.10")),)),
            "bracket rate must be between 0 and 1",
        ),
    ],
)
def test_calculate_tax_burden_rejects_malformed_federal_fields(
    federal,
    message,
):
    with pytest.raises(ValueError, match=re.escape(message)):
        calculate_tax_burden(TaxScenario(gross_income=money("1000")), federal=federal)


@pytest.mark.parametrize(
    ("federal", "message"),
    [
        (
            replace(FEDERAL_2026_SINGLE, standard_deduction=Decimal("NaN")),
            "standard_deduction must be a finite decimal",
        ),
        (
            federal_with_brackets((TaxBracket(money("0.00"), Decimal("-0.10")),)),
            "bracket rate must be between 0 and 1",
        ),
    ],
)
def test_build_income_series_rejects_malformed_federal_fields(
    federal,
    message,
):
    with pytest.raises(ValueError, match=re.escape(message)):
        build_income_series(start=0, stop=1000, step=1000, federal=federal)


@pytest.mark.parametrize(
    "calculate",
    [
        lambda federal: calculate_tax_burden(
            TaxScenario(gross_income=money("1000")), federal=federal
        ),
        lambda federal: build_income_series(
            start=0, stop=1000, step=1000, federal=federal
        ),
    ],
    ids=["calculate_tax_burden", "build_income_series"],
)
def test_public_boundaries_reject_unsupported_federal_filing_status(calculate):
    federal = replace(FEDERAL_2026_SINGLE, filing_status="qualifying_widow")

    with pytest.raises(
        ValueError,
        match=re.escape("unsupported filing_status: qualifying_widow"),
    ):
        calculate(federal)


def test_calculate_tax_burden_normalizes_custom_federal_money_fields():
    federal = FederalTaxParameters(
        tax_year=2026,
        filing_status="single",
        standard_deduction=Decimal("0.005"),
        brackets=(
            TaxBracket(Decimal("0.004"), Decimal("0.10")),
            TaxBracket(Decimal("100.005"), Decimal("0.12")),
        ),
    )
    normalized_federal = FederalTaxParameters(
        tax_year=2026,
        filing_status="single",
        standard_deduction=money("0.01"),
        brackets=(
            TaxBracket(money("0.00"), Decimal("0.10")),
            TaxBracket(money("100.01"), Decimal("0.12")),
        ),
    )
    no_pretax_deductions = replace(
        PRETAX_DEDUCTIONS_2026,
        employee_401k_limit=money("0.00"),
        health_fsa_limit=money("0.00"),
        dependent_care_fsa_limit=money("0.00"),
    )

    result = calculate_tax_burden(
        TaxScenario(gross_income=money("200")),
        federal=federal,
        pretax_deductions=no_pretax_deductions,
    )
    expected = calculate_tax_burden(
        TaxScenario(gross_income=money("200")),
        federal=normalized_federal,
        pretax_deductions=no_pretax_deductions,
    )

    assert result.federal_income_tax == expected.federal_income_tax


def test_build_income_series_normalizes_custom_federal_rate_fields():
    federal = federal_with_brackets((TaxBracket(money("0.00"), "0.10"),))
    no_pretax_deductions = replace(
        PRETAX_DEDUCTIONS_2026,
        employee_401k_limit=money("0.00"),
        health_fsa_limit=money("0.00"),
        dependent_care_fsa_limit=money("0.00"),
    )

    rows = build_income_series(
        start=1000,
        stop=1000,
        step=1,
        federal=federal,
        pretax_deductions=no_pretax_deductions,
    )

    assert rows[0].federal_income_tax == money("100.00")


def test_calculate_tax_burden_normalizes_custom_federal_money_field_types():
    federal = FederalTaxParameters(
        tax_year=2026,
        filing_status="single",
        standard_deduction=0.0,
        brackets=(TaxBracket(0.0, Decimal("0.10")),),
    )
    no_pretax_deductions = replace(
        PRETAX_DEDUCTIONS_2026,
        employee_401k_limit=money("0.00"),
        health_fsa_limit=money("0.00"),
        dependent_care_fsa_limit=money("0.00"),
    )

    result = calculate_tax_burden(
        TaxScenario(gross_income=money("1000")),
        federal=federal,
        pretax_deductions=no_pretax_deductions,
    )

    assert result.federal_income_tax == money("100.00")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "social_security_rate",
            Decimal("NaN"),
            "social_security_rate must be a finite decimal",
        ),
        (
            "medicare_rate",
            Decimal("-0.10"),
            "medicare_rate must be between 0 and 1",
        ),
        (
            "additional_medicare_rate",
            Decimal("1.10"),
            "additional_medicare_rate must be between 0 and 1",
        ),
        (
            "social_security_wage_base",
            Decimal("-1.00"),
            "social_security_wage_base must be non-negative",
        ),
        (
            "additional_medicare_threshold_single",
            Decimal("-1.00"),
            "additional_medicare_threshold_single must be non-negative",
        ),
        (
            "additional_medicare_thresholds",
            {"single": Decimal("-1.00")},
            "additional_medicare_threshold must be non-negative",
        ),
    ],
)
def test_calculate_tax_burden_rejects_malformed_payroll_parameters(
    field,
    value,
    message,
):
    payroll = replace(PAYROLL_2026, **{field: value})

    with pytest.raises(ValueError, match=re.escape(message)):
        calculate_tax_burden(TaxScenario(gross_income=money("1000")), payroll=payroll)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "social_security_rate",
            Decimal("NaN"),
            "social_security_rate must be a finite decimal",
        ),
        (
            "additional_medicare_thresholds",
            {"single": Decimal("-1.00")},
            "additional_medicare_threshold must be non-negative",
        ),
    ],
)
def test_build_income_series_rejects_malformed_payroll_parameters(
    field,
    value,
    message,
):
    payroll = replace(PAYROLL_2026, **{field: value})

    with pytest.raises(ValueError, match=re.escape(message)):
        build_income_series(start=0, stop=1000, step=1000, payroll=payroll)


@pytest.mark.parametrize(
    "calculate",
    [
        pytest.param(
            lambda **parameters: calculate_tax_burden(
                TaxScenario(gross_income=money("1000")),
                **parameters,
            ),
            id="calculate_tax_burden",
        ),
        pytest.param(
            lambda **parameters: build_income_series(
                start=0,
                stop=1000,
                step=1000,
                **parameters,
            ),
            id="build_income_series",
        ),
    ],
)
@pytest.mark.parametrize(
    ("field", "parameter_name"),
    [
        ("payroll", "payroll"),
        ("pretax_deductions", "pre-tax deduction"),
    ],
)
def test_public_boundaries_reject_mismatched_parameter_tax_years(
    calculate,
    field,
    parameter_name,
):
    parameters = {
        "federal": FEDERAL_2026_SINGLE,
        "payroll": PAYROLL_2026,
        "pretax_deductions": PRETAX_DEDUCTIONS_2026,
    }
    parameters[field] = replace(parameters[field], tax_year=2025)
    message = f"{parameter_name} tax_year 2025 does not match federal tax_year 2026"

    with pytest.raises(ValueError, match=re.escape(message)):
        calculate(**parameters)


@pytest.mark.parametrize(
    "calculate",
    [
        pytest.param(
            lambda **parameters: calculate_tax_burden(
                TaxScenario(gross_income=money("1000")),
                **parameters,
            ),
            id="calculate_tax_burden",
        ),
        pytest.param(
            lambda **parameters: build_income_series(
                start=0,
                stop=1000,
                step=1000,
                **parameters,
            ),
            id="build_income_series",
        ),
    ],
)
@pytest.mark.parametrize("tax_year", [-1, "2026", True])
def test_public_boundaries_reject_invalid_parameter_tax_years(
    calculate,
    tax_year,
):
    parameters = {
        "federal": replace(FEDERAL_2026_SINGLE, tax_year=tax_year),
        "payroll": replace(PAYROLL_2026, tax_year=tax_year),
        "pretax_deductions": replace(PRETAX_DEDUCTIONS_2026, tax_year=tax_year),
    }

    with pytest.raises(
        ValueError,
        match=re.escape("tax_year must be a non-negative integer"),
    ):
        calculate(**parameters)


def test_calculate_tax_burden_normalizes_custom_payroll_rate_fields():
    payroll = replace(
        PAYROLL_2026,
        social_security_rate="0.062",
        medicare_rate="0.0145",
        additional_medicare_rate="0.009",
    )
    scenario = TaxScenario(gross_income=money("250000"))

    result = calculate_tax_burden(scenario, payroll=payroll)
    expected = calculate_tax_burden(scenario, payroll=PAYROLL_2026)

    assert result.employee_social_security_tax == expected.employee_social_security_tax
    assert result.employee_medicare_tax == expected.employee_medicare_tax
    assert (
        result.employee_additional_medicare_tax
        == expected.employee_additional_medicare_tax
    )


def test_build_income_series_normalizes_custom_payroll_money_fields():
    payroll = replace(
        PAYROLL_2026,
        social_security_wage_base=184500.0,
        additional_medicare_threshold_single=200000.0,
        additional_medicare_thresholds={"single": 200000.0},
    )

    rows = build_income_series(start=250000, stop=250000, step=1, payroll=payroll)

    assert rows[0].employee_social_security_tax == money("11439.00")
    assert rows[0].employee_additional_medicare_tax == money("419.40")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "employee_401k_limit",
            Decimal("NaN"),
            "employee_401k_limit must be a finite decimal",
        ),
        (
            "health_fsa_limit",
            Decimal("-1.00"),
            "health_fsa_limit must be non-negative",
        ),
        (
            "dependent_care_fsa_limit",
            Decimal("-1.00"),
            "dependent_care_fsa_limit must be non-negative",
        ),
        (
            "gradual_phase_in_start_rate",
            Decimal("1.10"),
            "gradual_phase_in_start_rate must be between 0 and 1",
        ),
    ],
)
def test_calculate_tax_burden_rejects_malformed_pretax_parameters(
    field,
    value,
    message,
):
    pretax = replace(PRETAX_DEDUCTIONS_2026, **{field: value})

    with pytest.raises(ValueError, match=re.escape(message)):
        calculate_tax_burden(
            TaxScenario(gross_income=money("1000")),
            pretax_deductions=pretax,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "employee_401k_limit",
            Decimal("NaN"),
            "employee_401k_limit must be a finite decimal",
        ),
        (
            "gradual_phase_in_start_rate",
            Decimal("-0.10"),
            "gradual_phase_in_start_rate must be between 0 and 1",
        ),
    ],
)
def test_build_income_series_rejects_malformed_pretax_parameters(
    field,
    value,
    message,
):
    pretax = replace(PRETAX_DEDUCTIONS_2026, **{field: value})

    with pytest.raises(ValueError, match=re.escape(message)):
        build_income_series(
            start=0,
            stop=1000,
            step=1000,
            pretax_deductions=pretax,
        )


def test_calculate_tax_burden_normalizes_custom_pretax_money_fields():
    pretax = replace(
        PRETAX_DEDUCTIONS_2026,
        employee_401k_limit=24500.0,
        health_fsa_limit=3400.0,
        dependent_care_fsa_limit=7500.0,
    )
    scenario = TaxScenario(gross_income=money("100000"), dependent_count=1)

    result = calculate_tax_burden(scenario, pretax_deductions=pretax)
    expected = calculate_tax_burden(scenario, pretax_deductions=PRETAX_DEDUCTIONS_2026)

    assert result.total_pretax_deductions == expected.total_pretax_deductions
    assert result.federal_income_tax == expected.federal_income_tax
    assert result.total_employee_tax == expected.total_employee_tax


def test_build_income_series_normalizes_custom_pretax_rate_field():
    pretax = replace(
        PRETAX_DEDUCTIONS_2026,
        gradual_phase_in_start_rate="0.01",
    )
    expected = replace(
        PRETAX_DEDUCTIONS_2026,
        gradual_phase_in_start_rate=Decimal("0.01"),
    )

    rows = build_income_series(
        start=100000,
        stop=100000,
        step=1,
        pretax_deduction_mode="gradual_phase_in",
        pretax_deductions=pretax,
    )

    normalized_rows = build_income_series(
        start=100000,
        stop=100000,
        step=1,
        pretax_deduction_mode="gradual_phase_in",
        pretax_deductions=expected,
    )

    assert rows[0].total_pretax_deductions == normalized_rows[0].total_pretax_deductions


def test_dependent_care_fsa_activates_when_dependents_are_present():
    result = calculate_tax_burden(
        TaxScenario(gross_income=money("100000"), dependent_count=1)
    )

    assert result.employee_401k_contribution == money("24500.00")
    assert result.health_fsa_contribution == money("3400.00")
    assert result.dependent_care_fsa_contribution == money("7500.00")
    assert result.total_pretax_deductions == money("35400.00")
    assert result.taxable_income == money("48500.00")
    assert result.federal_income_tax == money("5572.00")
    assert result.employee_social_security_tax == money("5524.20")
    assert result.employee_medicare_tax == money("1291.95")
    assert result.total_employee_tax == money("12388.15")
    assert result.marginal_employee_tax_rate == Decimal("0.1965")


def test_social_security_tax_is_capped_at_2026_wage_base():
    result = calculate_tax_burden(TaxScenario(gross_income=money("250000")))

    assert result.employee_social_security_tax == money("11439.00")
    assert result.employee_medicare_tax == money("3575.70")
    assert result.employee_additional_medicare_tax == money("419.40")


def test_payroll_parameters_accept_legacy_single_additional_medicare_threshold():
    payroll = PayrollTaxParameters(
        tax_year=2026,
        social_security_rate=Decimal("0.062"),
        social_security_wage_base=money("184500.00"),
        medicare_rate=Decimal("0.0145"),
        additional_medicare_rate=Decimal("0.009"),
        additional_medicare_threshold_single=money("200000.00"),
    )

    result = calculate_tax_burden(
        TaxScenario(gross_income=money("250000")),
        payroll=payroll,
    )

    assert payroll.additional_medicare_thresholds == {}
    assert result.employee_additional_medicare_tax == money("419.40")


@pytest.mark.parametrize(
    "calculate",
    [
        lambda payroll: calculate_tax_burden(
            TaxScenario(gross_income=money("250000")),
            payroll=payroll,
        ),
        lambda payroll: build_income_series(
            start=0,
            stop=250000,
            step=250000,
            payroll=payroll,
        ),
    ],
    ids=["calculate_tax_burden", "build_income_series"],
)
def test_single_filing_status_rejects_conflicting_additional_medicare_thresholds(
    calculate,
):
    payroll = PayrollTaxParameters(
        tax_year=2026,
        social_security_rate=Decimal("0.062"),
        social_security_wage_base=money("184500.00"),
        medicare_rate=Decimal("0.0145"),
        additional_medicare_rate=Decimal("0.009"),
        additional_medicare_threshold_single=money("200000.00"),
        additional_medicare_thresholds={"single": money("250000.00")},
    )

    with pytest.raises(
        ValueError,
        match=(
            "additional_medicare_threshold_single 200000.00 does not match "
            "additional_medicare_threshold for 2026 single"
        ),
    ):
        calculate(payroll)


@pytest.mark.parametrize(
    "calculate",
    [
        lambda payroll: calculate_tax_burden(
            TaxScenario(gross_income=money("300000")),
            federal=FEDERAL_2026_MARRIED_JOINT,
            payroll=payroll,
        ),
        lambda payroll: build_income_series(
            start=0,
            stop=300000,
            step=100000,
            federal=FEDERAL_2026_MARRIED_JOINT,
            payroll=payroll,
        ),
    ],
    ids=["calculate_tax_burden", "build_income_series"],
)
def test_non_single_filing_status_requires_additional_medicare_threshold(calculate):
    payroll = PayrollTaxParameters(
        tax_year=2026,
        social_security_rate=Decimal("0.062"),
        social_security_wage_base=money("184500.00"),
        medicare_rate=Decimal("0.0145"),
        additional_medicare_rate=Decimal("0.009"),
        additional_medicare_threshold_single=money("200000.00"),
    )

    with pytest.raises(
        ValueError,
        match="additional_medicare_threshold missing for 2026 married_joint",
    ):
        calculate(payroll)


def test_can_include_employer_payroll_tax_for_economic_burden_view():
    result = calculate_tax_burden(
        TaxScenario(gross_income=money("250000"), include_employer_payroll_tax=True)
    )

    assert result.employer_social_security_tax == money("11439.00")
    assert result.employer_medicare_tax == money("3575.70")
    assert result.total_employer_payroll_tax == money("15014.70")
    assert result.total_tax_with_employer_payroll == money("72824.80")


def test_dual_earner_payroll_breakdown_shows_employee_and_employer_taxes_by_worker():
    result = calculate_tax_burden(
        TaxScenario(
            gross_income=money("300000"),
            secondary_income=money("150000"),
            include_employer_payroll_tax=True,
        ),
        federal=FEDERAL_2026_MARRIED_JOINT,
    )

    assert [
        (
            row.label,
            row.gross_income,
            row.employee_social_security_tax,
            row.employee_medicare_tax,
            row.employee_additional_medicare_tax,
            row.total_employee_payroll_tax,
            row.employer_social_security_tax,
            row.employer_medicare_tax,
            row.total_employer_payroll_tax,
            row.total_payroll_tax,
        )
        for row in result.payroll_breakdown
    ] == [
        (
            "Income 1",
            money("150000.00"),
            money("9089.20"),
            money("2125.70"),
            money("194.40"),
            money("11409.30"),
            money("9089.20"),
            money("2125.70"),
            money("11214.90"),
            money("22624.20"),
        ),
        (
            "Income 2",
            money("150000.00"),
            money("9089.20"),
            money("2125.70"),
            money("194.40"),
            money("11409.30"),
            money("9089.20"),
            money("2125.70"),
            money("11214.90"),
            money("22624.20"),
        ),
        (
            "Total",
            money("300000.00"),
            money("18178.40"),
            money("4251.40"),
            money("388.80"),
            money("22818.60"),
            money("18178.40"),
            money("4251.40"),
            money("22429.80"),
            money("45248.40"),
        ),
    ]


def test_dual_earner_deductions_are_limited_by_each_workers_income():
    result = calculate_tax_burden(
        TaxScenario(
            gross_income=money("300000"),
            secondary_income=money("5000"),
            include_employer_payroll_tax=True,
        ),
        federal=FEDERAL_2026_MARRIED_JOINT,
    )

    assert result.employee_401k_contribution == money("28890.68")
    assert result.health_fsa_contribution == money("4009.32")
    assert result.total_pretax_deductions == money("32900.00")
    assert [
        (row.label, row.gross_income, row.payroll_wages)
        for row in result.payroll_breakdown
    ] == [
        ("Income 1", money("295000.00"), money("291600.00")),
        ("Income 2", money("5000.00"), money("4390.68")),
        ("Total", money("300000.00"), money("295990.68")),
    ]
    assert result.employee_social_security_tax == money("11711.22")


def test_gradual_phase_in_starts_after_standard_deduction_and_reaches_caps():
    at_standard_deduction = calculate_tax_burden(
        TaxScenario(
            gross_income=money("16100"),
            pretax_deduction_mode="gradual_phase_in",
        )
    )
    partial = calculate_tax_burden(
        TaxScenario(
            gross_income=money("100000"),
            pretax_deduction_mode="gradual_phase_in",
        )
    )
    fully_phased_in = calculate_tax_burden(
        TaxScenario(
            gross_income=money("300225"),
            pretax_deduction_mode="gradual_phase_in",
        )
    )

    assert at_standard_deduction.total_pretax_deductions == money("0.00")
    assert partial.total_pretax_deductions == money("3448.87")
    assert partial.employee_401k_contribution == money("3028.58")
    assert partial.health_fsa_contribution == money("420.29")
    assert partial.taxable_income == money("80451.13")
    assert partial.total_employee_tax == money("20029.10")
    assert partial.marginal_employee_tax_rate == Decimal("0.2819")
    assert fully_phased_in.employee_401k_contribution == money("24500.00")
    assert fully_phased_in.health_fsa_contribution == money("3400.00")
    assert fully_phased_in.total_pretax_deductions == money("27900.00")


def test_unknown_pretax_deduction_mode_is_rejected():
    with pytest.raises(ValueError, match="pretax_deduction_mode"):
        calculate_tax_burden(
            TaxScenario(
                gross_income=money("100000"),
                pretax_deduction_mode="unknown",
            )
        )


def test_build_income_series_samples_inclusive_income_range():
    rows = build_income_series(start=0, stop=100000, step=50000)

    assert [row.gross_income for row in rows] == [
        money("0.00"),
        money("50000.00"),
        money("100000.00"),
    ]


def test_dual_earner_series_marginal_rates_follow_configured_income_split():
    federal = FederalTaxParameters(
        tax_year=2026,
        filing_status="married_joint",
        standard_deduction=money("0.00"),
        brackets=(TaxBracket(money("0.00"), Decimal("0.10")),),
    )
    no_pretax_deductions = replace(
        PRETAX_DEDUCTIONS_2026,
        employee_401k_limit=money("0.00"),
        health_fsa_limit=money("0.00"),
        dependent_care_fsa_limit=money("0.00"),
    )

    rows = build_income_series(
        start=money("184500.00"),
        stop=money("200000.00"),
        step=money("15500.00"),
        include_employer_payroll_tax=True,
        secondary_income=money("200000.00"),
        federal=federal,
        pretax_deductions=no_pretax_deductions,
    )

    assert [
        (
            row.gross_income,
            row.marginal_employee_tax_rate,
            row.marginal_tax_rate_with_employer_payroll,
        )
        for row in rows
    ] == [
        (money("184500.00"), Decimal("0.1145"), Decimal("0.1290")),
        (money("200000.00"), Decimal("0.1765"), Decimal("0.2530")),
    ]


def test_dual_earner_series_includes_secondary_income_marginal_breakpoint():
    federal = FederalTaxParameters(
        tax_year=2026,
        filing_status="married_joint",
        standard_deduction=money("0.00"),
        brackets=(TaxBracket(money("0.00"), Decimal("0.10")),),
    )
    no_pretax_deductions = replace(
        PRETAX_DEDUCTIONS_2026,
        employee_401k_limit=money("0.00"),
        health_fsa_limit=money("0.00"),
        dependent_care_fsa_limit=money("0.00"),
    )

    rows = build_income_series(
        start=money("0.00"),
        stop=money("400000.00"),
        step=money("120000.00"),
        include_marginal_breakpoints=True,
        secondary_income=money("200000.00"),
        federal=federal,
        pretax_deductions=no_pretax_deductions,
    )

    rates_by_income = {
        row.gross_income: row.marginal_employee_tax_rate for row in rows
    }
    assert rates_by_income[money("184500.00")] == Decimal("0.1145")
    assert rates_by_income[money("200000.00")] == Decimal("0.1765")


def test_dual_earner_series_marginal_rate_uses_next_worker_pretax_caps():
    federal = FederalTaxParameters(
        tax_year=2026,
        filing_status="married_joint",
        standard_deduction=money("0.00"),
        brackets=(TaxBracket(money("0.00"), Decimal("0.10")),),
    )
    pretax_deductions = replace(
        PRETAX_DEDUCTIONS_2026,
        employee_401k_limit=money("1.00"),
        health_fsa_limit=money("0.00"),
        dependent_care_fsa_limit=money("0.00"),
    )

    rows = build_income_series(
        start=money("0.00"),
        stop=money("1.00"),
        step=money("1.00"),
        include_employer_payroll_tax=True,
        pretax_deduction_mode="gradual_phase_in",
        secondary_income=money("1.00"),
        federal=federal,
        pretax_deductions=pretax_deductions,
    )

    assert rows[0].marginal_employee_tax_rate == Decimal("0.0873")
    assert rows[0].marginal_tax_rate_with_employer_payroll == Decimal("0.1638")


def test_direct_dual_earner_marginal_rate_keeps_secondary_income_fixed():
    federal = FederalTaxParameters(
        tax_year=2026,
        filing_status="married_joint",
        standard_deduction=money("0.00"),
        brackets=(TaxBracket(money("0.00"), Decimal("0.10")),),
    )
    no_pretax_deductions = replace(
        PRETAX_DEDUCTIONS_2026,
        employee_401k_limit=money("0.00"),
        health_fsa_limit=money("0.00"),
        dependent_care_fsa_limit=money("0.00"),
    )

    result = calculate_tax_burden(
        TaxScenario(
            gross_income=money("184500.00"),
            secondary_income=money("184500.00"),
            include_employer_payroll_tax=True,
        ),
        federal=federal,
        pretax_deductions=no_pretax_deductions,
    )

    assert result.marginal_employee_tax_rate == Decimal("0.1765")
    assert result.marginal_tax_rate_with_employer_payroll == Decimal("0.2530")


def test_build_income_series_can_include_exact_marginal_rate_change_points():
    rows = build_income_series(
        start=0,
        stop=250000,
        step=100000,
        include_marginal_breakpoints=True,
    )

    assert [row.gross_income for row in rows] == [
        money("0.00"),
        money("27900.00"),
        money("44000.00"),
        money("56400.00"),
        money("94400.00"),
        money("100000.00"),
        money("149700.00"),
        money("187900.00"),
        money("200000.00"),
        money("203400.00"),
        money("245775.00"),
        money("250000.00"),
    ]


def test_build_income_series_includes_high_income_marginal_breakpoint():
    federal = FederalTaxParameters(
        tax_year=2026,
        filing_status="single",
        standard_deduction=money("0.00"),
        brackets=(
            TaxBracket(money("0.00"), Decimal("0.10")),
            TaxBracket(money("600000000.00"), Decimal("0.20")),
        ),
    )

    rows = build_income_series(
        start=money("0.00"),
        stop=money("700000000.00"),
        step=money("700000000.00"),
        include_marginal_breakpoints=True,
        federal=federal,
    )

    rates_by_income = {
        row.gross_income: row.marginal_employee_tax_rate for row in rows
    }
    assert rates_by_income[money("600027900.00")] == Decimal("0.2235")


def test_build_income_series_rounds_high_income_breakpoint_up_to_first_cent():
    federal = FederalTaxParameters(
        tax_year=2026,
        filing_status="single",
        standard_deduction=money("0.00"),
        brackets=(
            TaxBracket(money("0.00"), Decimal("0.10")),
            TaxBracket(money("2e9"), Decimal("0.20")),
            TaxBracket(money("1e10"), Decimal("0.30")),
            TaxBracket(money("2e10"), Decimal("0.40")),
        ),
    )
    pretax_deductions = replace(
        PRETAX_DEDUCTIONS_2026,
        employee_401k_limit=money("1e10"),
        health_fsa_limit=money("0.00"),
        dependent_care_fsa_limit=money("0.00"),
    )

    rows = build_income_series(
        start=money("0.00"),
        stop=money("3e10"),
        step=money("3e10"),
        include_marginal_breakpoints=True,
        pretax_deduction_mode="gradual_phase_in",
        federal=federal,
        pretax_deductions=pretax_deductions,
    )

    assert money("2132771177.75") in {row.gross_income for row in rows}


def test_build_income_series_keeps_large_marginal_breakpoint_cent_precision():
    federal = FederalTaxParameters(
        tax_year=2026,
        filing_status="single",
        standard_deduction=money("0.00"),
        brackets=(
            TaxBracket(money("0.00"), Decimal("0.10")),
            TaxBracket(money("6e24"), Decimal("0.20")),
        ),
    )

    rows = build_income_series(
        start=money("0.00"),
        stop=money("7e24"),
        step=money("7e24"),
        include_marginal_breakpoints=True,
        federal=federal,
    )

    assert money("6000000000000000000027900.00") in {
        row.gross_income for row in rows
    }


def test_build_income_series_probes_maximum_money_after_doubling_overflow():
    federal = FederalTaxParameters(
        tax_year=2026,
        filing_status="single",
        standard_deduction=money("0.01"),
        brackets=(
            TaxBracket(money("0.00"), Decimal("0.10")),
            TaxBracket(money("5e25"), Decimal("0.20")),
        ),
    )
    no_pretax_deductions = replace(
        PRETAX_DEDUCTIONS_2026,
        employee_401k_limit=money("0.00"),
        health_fsa_limit=money("0.00"),
        dependent_care_fsa_limit=money("0.00"),
    )

    rows = build_income_series(
        start=money("5e25"),
        stop=money("6e25"),
        step=money("1e25"),
        include_marginal_breakpoints=True,
        pretax_deduction_mode="gradual_phase_in",
        federal=federal,
        pretax_deductions=no_pretax_deductions,
    )

    assert money("50000000000000000000000000.01") in {
        row.gross_income for row in rows
    }


def test_build_income_series_includes_dependent_care_breakpoints():
    rows = build_income_series(
        start=0,
        stop=250000,
        step=100000,
        include_marginal_breakpoints=True,
        dependent_count=1,
    )

    assert [row.gross_income for row in rows] == [
        money("0.00"),
        money("35400.00"),
        money("51500.00"),
        money("63900.00"),
        money("100000.00"),
        money("101900.00"),
        money("157200.00"),
        money("195400.00"),
        money("200000.00"),
        money("210900.00"),
        money("250000.00"),
    ]


def test_build_income_series_includes_lopsided_dual_earner_deduction_breakpoint():
    rows = build_income_series(
        start=0,
        stop=120000,
        step=120000,
        include_marginal_breakpoints=True,
        secondary_income=money("5000"),
        federal=FEDERAL_2026_MARRIED_JOINT,
    )

    assert [row.gross_income for row in rows] == [
        money("0.00"),
        money("5000.00"),
        money("32900.00"),
        money("65100.00"),
        money("89900.00"),
        money("120000.00"),
    ]
    deductions_by_income = {
        row.gross_income: row.total_pretax_deductions for row in rows
    }
    assert deductions_by_income[money("32900.00")] == money("32900.00")


def test_build_income_series_can_include_gradual_phase_in_breakpoints():
    rows = build_income_series(
        start=0,
        stop=250000,
        step=100000,
        include_marginal_breakpoints=True,
        pretax_deduction_mode="gradual_phase_in",
    )

    assert [row.gross_income for row in rows] == [
        money("0.00"),
        money("16100.00"),
        money("28896.91"),
        money("68220.02"),
        money("100000.00"),
        money("127196.55"),
        money("185848.62"),
        money("200000.00"),
        money("201575.50"),
        money("235279.59"),
        money("250000.00"),
    ]


def test_build_income_series_rejects_reversed_income_range():
    with pytest.raises(ValueError, match="start must be less than or equal to stop"):
        build_income_series(start=100000, stop=0, step=10000)


def test_build_income_series_rejects_secondary_income_above_stop():
    with pytest.raises(ValueError, match="secondary_income cannot exceed stop"):
        build_income_series(
            start=0,
            stop=money("100000"),
            step=money("50000"),
            secondary_income=money("120000"),
            federal=FEDERAL_2026_MARRIED_JOINT,
        )


def test_build_income_series_rejects_sub_cent_negative_start():
    with pytest.raises(ValueError, match="income bounds must be non-negative"):
        build_income_series(start=money("-0.004"), stop=0, step=1)


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("start", {"start": money("NaN"), "stop": 0, "step": 1}),
        ("stop", {"start": 0, "stop": money("Infinity"), "step": 1}),
        ("step", {"start": 0, "stop": 1, "step": money("NaN")}),
        (
            "secondary_income",
            {
                "start": 0,
                "stop": 1,
                "step": 1,
                "secondary_income": money("NaN"),
                "federal": FEDERAL_2026_MARRIED_JOINT,
            },
        ),
    ],
)
def test_build_income_series_rejects_non_finite_money_inputs(field, kwargs):
    with pytest.raises(ValueError, match=f"{field} must be a finite decimal"):
        build_income_series(**kwargs)


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("start", {"start": money("1e27"), "stop": 1, "step": 1}),
        ("stop", {"start": 0, "stop": money("1e27"), "step": 1}),
        ("step", {"start": 0, "stop": 1, "step": money("1e27")}),
        (
            "secondary_income",
            {
                "start": 0,
                "stop": 1,
                "step": 1,
                "secondary_income": money("1e27"),
                "federal": FEDERAL_2026_MARRIED_JOINT,
            },
        ),
    ],
)
def test_build_income_series_rejects_unroundable_money_inputs(field, kwargs):
    with pytest.raises(ValueError, match=f"{field} must fit cents precision"):
        build_income_series(**kwargs)


def test_build_income_series_rejects_excessive_row_count():
    with pytest.raises(ValueError, match="at most 2001 rows"):
        build_income_series(start=0, stop=2001000, step=1000)


def test_build_income_series_rejects_excessive_row_count_without_scanning_full_range(
    monkeypatch,
):
    original_money = tax_module._money
    money_calls = 0

    def guarded_money(value, field_name="money"):
        nonlocal money_calls
        money_calls += 1
        if money_calls > 30:
            raise AssertionError("row limit was not enforced promptly")
        return original_money(value, field_name)

    monkeypatch.setattr(tax_module, "MAX_INCOME_SERIES_ROWS", 3)
    monkeypatch.setattr(tax_module, "_money", guarded_money)

    with pytest.raises(ValueError, match="at most 3 rows"):
        tax_module.build_income_series(start=0, stop=1000000, step=1)


@pytest.mark.parametrize("income", [money("-1"), money("-0.01"), money("-0.004")])
def test_negative_income_is_rejected(income):
    with pytest.raises(ValueError, match="gross_income"):
        calculate_tax_burden(TaxScenario(gross_income=income))


@pytest.mark.parametrize("income", [money("NaN"), money("Infinity")])
def test_non_finite_income_is_rejected(income):
    with pytest.raises(ValueError, match="gross_income must be a finite decimal"):
        calculate_tax_burden(TaxScenario(gross_income=income))


def test_unroundable_income_is_rejected():
    with pytest.raises(ValueError, match="gross_income must fit cents precision"):
        calculate_tax_burden(TaxScenario(gross_income=money("1e27")))


def test_sub_cent_negative_secondary_income_is_rejected():
    with pytest.raises(ValueError, match="secondary_income must be non-negative"):
        calculate_tax_burden(
            TaxScenario(
                gross_income=money("100000"),
                secondary_income=money("-0.004"),
            ),
            federal=FEDERAL_2026_MARRIED_JOINT,
        )


def test_non_finite_secondary_income_is_rejected():
    with pytest.raises(ValueError, match="secondary_income must be a finite decimal"):
        calculate_tax_burden(
            TaxScenario(
                gross_income=money("100000"),
                secondary_income=money("NaN"),
            ),
            federal=FEDERAL_2026_MARRIED_JOINT,
        )


def test_unroundable_secondary_income_is_rejected():
    with pytest.raises(ValueError, match="secondary_income must fit cents precision"):
        calculate_tax_burden(
            TaxScenario(
                gross_income=money("100000"),
                secondary_income=money("1e27"),
            ),
            federal=FEDERAL_2026_MARRIED_JOINT,
        )


def test_negative_dependent_count_is_rejected():
    with pytest.raises(ValueError, match="dependent_count"):
        calculate_tax_burden(
            TaxScenario(gross_income=money("100000"), dependent_count=-1)
        )


@pytest.mark.parametrize("dependent_count", ["1", 1.5, Decimal("1"), True])
def test_calculate_tax_burden_rejects_non_integer_dependent_count(dependent_count):
    with pytest.raises(ValueError, match="dependent_count must be an integer"):
        calculate_tax_burden(
            TaxScenario(
                gross_income=money("100000"),
                dependent_count=dependent_count,
            )
        )


@pytest.mark.parametrize("dependent_count", ["1", 1.5, Decimal("1"), True])
def test_build_income_series_rejects_non_integer_dependent_count(dependent_count):
    with pytest.raises(ValueError, match="dependent_count must be an integer"):
        build_income_series(
            start=0,
            stop=1000,
            step=1000,
            dependent_count=dependent_count,
        )


@pytest.mark.parametrize("include_employer_payroll_tax", ["true", "false", 1, 0])
def test_calculate_tax_burden_rejects_non_boolean_employer_payroll_flag(
    include_employer_payroll_tax,
):
    with pytest.raises(
        ValueError,
        match="include_employer_payroll_tax must be boolean",
    ):
        calculate_tax_burden(
            TaxScenario(
                gross_income=money("100000"),
                include_employer_payroll_tax=include_employer_payroll_tax,
            )
        )


@pytest.mark.parametrize(
    "flag_name",
    ["include_employer_payroll_tax", "include_marginal_breakpoints"],
)
@pytest.mark.parametrize("flag_value", ["true", "false", 1, 0])
def test_build_income_series_rejects_non_boolean_flags(
    flag_name,
    flag_value,
):
    with pytest.raises(
        ValueError,
        match=f"{flag_name} must be boolean",
    ):
        build_income_series(
            start=0,
            stop=1000,
            step=1000,
            **{flag_name: flag_value},
        )
