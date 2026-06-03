from decimal import Decimal

import pytest

from tax_explorer import (
    FEDERAL_2026_SINGLE,
    TaxScenario,
    build_income_series,
    calculate_tax_burden,
)


def money(value: str) -> Decimal:
    return Decimal(value)


def test_standard_deduction_eliminates_income_tax_below_threshold():
    result = calculate_tax_burden(TaxScenario(gross_income=money("10000")))

    assert result.federal_income_tax == money("0.00")
    assert result.employee_social_security_tax == money("620.00")
    assert result.employee_medicare_tax == money("145.00")
    assert result.employee_additional_medicare_tax == money("0.00")
    assert result.total_employee_tax == money("765.00")


def test_federal_income_tax_uses_progressive_2026_single_brackets_after_standard_deduction():
    result = calculate_tax_burden(TaxScenario(gross_income=money("100000")))

    assert FEDERAL_2026_SINGLE.standard_deduction == money("16100.00")
    assert result.taxable_income == money("83900.00")
    assert result.federal_income_tax == money("13170.00")
    assert result.total_employee_tax == money("20820.00")
    assert result.effective_employee_tax_rate == Decimal("0.2082")


def test_social_security_tax_is_capped_at_2026_wage_base():
    result = calculate_tax_burden(TaxScenario(gross_income=money("250000")))

    assert result.employee_social_security_tax == money("11439.00")
    assert result.employee_medicare_tax == money("3625.00")
    assert result.employee_additional_medicare_tax == money("450.00")


def test_can_include_employer_payroll_tax_for_economic_burden_view():
    result = calculate_tax_burden(
        TaxScenario(gross_income=money("250000"), include_employer_payroll_tax=True)
    )

    assert result.employer_social_security_tax == money("11439.00")
    assert result.employer_medicare_tax == money("3625.00")
    assert result.total_employer_payroll_tax == money("15064.00")
    assert result.total_tax_with_employer_payroll == money("81882.00")


def test_build_income_series_samples_inclusive_income_range():
    rows = build_income_series(start=0, stop=100000, step=50000)

    assert [row.gross_income for row in rows] == [
        money("0.00"),
        money("50000.00"),
        money("100000.00"),
    ]


@pytest.mark.parametrize("income", [money("-1"), money("-0.01")])
def test_negative_income_is_rejected(income):
    with pytest.raises(ValueError, match="gross_income"):
        calculate_tax_burden(TaxScenario(gross_income=income))
