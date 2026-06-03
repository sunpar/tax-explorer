from decimal import Decimal

from tax_explorer import TaxScenario, calculate_tax_burden
from tax_explorer.database import (
    get_available_tax_years,
    get_filing_statuses,
    initialize_database,
    load_federal_tax_parameters,
    load_payroll_tax_parameters,
)


def test_initializes_seeded_tax_years(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        years = get_available_tax_years(connection)

    assert years == [2026]


def test_loads_2026_single_filer_federal_parameters_from_sqlite(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        federal = load_federal_tax_parameters(connection, 2026, "single")

    assert federal.tax_year == 2026
    assert federal.filing_status == "single"
    assert federal.standard_deduction == Decimal("16100.00")
    assert federal.brackets[0].lower_bound == Decimal("0.00")
    assert federal.brackets[0].rate == Decimal("0.10")
    assert federal.brackets[-1].lower_bound == Decimal("640600.00")
    assert federal.brackets[-1].rate == Decimal("0.37")


def test_loads_all_supported_2026_filing_statuses_from_sqlite(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        statuses = get_filing_statuses(connection, 2026)
        federal_by_status = {
            status["code"]: load_federal_tax_parameters(connection, 2026, status["code"])
            for status in statuses
        }

    assert statuses == [
        {"code": "single", "label": "Single"},
        {"code": "married_joint", "label": "Married filing jointly"},
        {"code": "married_separate", "label": "Married filing separately"},
        {"code": "head_of_household", "label": "Head of household"},
    ]
    assert federal_by_status["single"].standard_deduction == Decimal("16100.00")
    assert federal_by_status["single"].brackets[-1].lower_bound == Decimal("640600.00")
    assert federal_by_status["married_joint"].standard_deduction == Decimal("32200.00")
    assert federal_by_status["married_joint"].brackets[1].lower_bound == Decimal(
        "24800.00"
    )
    assert federal_by_status["married_joint"].brackets[-1].lower_bound == Decimal(
        "768700.00"
    )
    assert federal_by_status["married_separate"].standard_deduction == Decimal(
        "16100.00"
    )
    assert federal_by_status["married_separate"].brackets[-1].lower_bound == Decimal(
        "384350.00"
    )
    assert federal_by_status["head_of_household"].standard_deduction == Decimal(
        "24150.00"
    )
    assert federal_by_status["head_of_household"].brackets[1].lower_bound == Decimal(
        "17700.00"
    )
    assert federal_by_status["head_of_household"].brackets[-1].lower_bound == Decimal(
        "640600.00"
    )


def test_loads_2026_payroll_parameters_from_sqlite(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        payroll = load_payroll_tax_parameters(connection, 2026)

    assert payroll.social_security_rate == Decimal("0.062")
    assert payroll.social_security_wage_base == Decimal("184500.00")
    assert payroll.medicare_rate == Decimal("0.0145")
    assert payroll.additional_medicare_rate == Decimal("0.009")
    assert payroll.additional_medicare_threshold_single == Decimal("200000.00")


def test_calculator_accepts_database_loaded_parameters(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        federal = load_federal_tax_parameters(connection, 2026, "single")
        payroll = load_payroll_tax_parameters(connection, 2026)

    result = calculate_tax_burden(
        TaxScenario(gross_income=Decimal("100000")),
        federal=federal,
        payroll=payroll,
    )

    assert result.taxable_income == Decimal("83900.00")
    assert result.total_employee_tax == Decimal("20820.00")
