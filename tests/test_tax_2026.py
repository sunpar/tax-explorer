from decimal import Decimal

import pytest
import tax_explorer as tax_module

from tax_explorer import (
    FEDERAL_2026_SINGLE,
    FederalTaxParameters,
    PayrollTaxParameters,
    TaxBracket,
    TaxScenario,
    build_income_series,
    calculate_tax_burden,
)


def money(value: str) -> Decimal:
    return Decimal(value)


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
        money("32900.00"),
        money("65100.00"),
        money("89900.00"),
        money("120000.00"),
    ]
    assert rows[1].total_pretax_deductions == money("32900.00")


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
        money("28896.90"),
        money("68220.02"),
        money("100000.00"),
        money("127196.54"),
        money("185848.61"),
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


def test_build_income_series_rejects_excessive_row_count():
    with pytest.raises(ValueError, match="at most 2001 rows"):
        build_income_series(start=0, stop=2001000, step=1000)


def test_build_income_series_rejects_excessive_row_count_without_scanning_full_range(
    monkeypatch,
):
    original_money = tax_module._money
    money_calls = 0

    def guarded_money(value):
        nonlocal money_calls
        money_calls += 1
        if money_calls > 12:
            raise AssertionError("row limit was not enforced promptly")
        return original_money(value)

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


def test_negative_dependent_count_is_rejected():
    with pytest.raises(ValueError, match="dependent_count"):
        calculate_tax_burden(
            TaxScenario(gross_income=money("100000"), dependent_count=-1)
        )
