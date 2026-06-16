import sqlite3
from decimal import Decimal

import pytest

from tax_explorer import TaxScenario, calculate_tax_burden
from tax_explorer.database import (
    connect,
    get_available_tax_years,
    get_filing_statuses,
    initialize_database,
    load_federal_tax_parameters,
    load_payroll_tax_parameters,
    load_pretax_deduction_parameters,
)


def insert_federal_tax_parameters(
    connection: sqlite3.Connection, year: int, filing_status: str
) -> None:
    connection.execute(
        """
        INSERT INTO federal_tax_parameters
            (year, filing_status, standard_deduction)
        VALUES (?, ?, ?)
        """,
        (year, filing_status, "0.00"),
    )


def test_initializes_seeded_tax_years(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        years = get_available_tax_years(connection)

    assert years == [2026]


def test_connection_enforces_foreign_keys(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]

        assert foreign_keys_enabled == 1
        with pytest.raises(sqlite3.IntegrityError):
            insert_federal_tax_parameters(connection, 2099, "single")
        with pytest.raises(sqlite3.IntegrityError):
            insert_federal_tax_parameters(connection, 2026, "qualifying_widow")


def test_connect_enables_foreign_keys_for_existing_database(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    initialize_database(db_path).close()

    with connect(db_path) as connection:
        foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]

        assert foreign_keys_enabled == 1
        with pytest.raises(sqlite3.IntegrityError):
            insert_federal_tax_parameters(connection, 2099, "single")


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


@pytest.mark.parametrize("standard_deduction", ["-1.00", "-0.004"])
def test_rejects_negative_federal_standard_deduction_from_sqlite(
    tmp_path,
    standard_deduction,
):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        connection.execute(
            """
            UPDATE federal_tax_parameters
            SET standard_deduction = ?
            WHERE year = ? AND filing_status = ?
            """,
            (standard_deduction, 2026, "single"),
        )
        connection.commit()

        with pytest.raises(ValueError, match="standard_deduction must be non-negative"):
            load_federal_tax_parameters(connection, 2026, "single")


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("lower_bound", "-1.00"),
        ("lower_bound", "-0.004"),
        ("rate", "-0.10"),
        ("rate", "1.10"),
    ],
)
def test_rejects_invalid_federal_brackets_from_sqlite(
    tmp_path,
    column,
    value,
):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        connection.execute(
            f"""
            UPDATE federal_tax_brackets
            SET {column} = ?
            WHERE year = ? AND filing_status = ? AND lower_bound = ?
            """,
            (value, 2026, "single", "0.00"),
        )
        connection.commit()

        messages = {
            "lower_bound": "bracket lower_bound must be non-negative",
            "rate": "bracket rate must be between 0 and 1",
        }
        with pytest.raises(ValueError, match=messages[column]):
            load_federal_tax_parameters(connection, 2026, "single")


def test_loads_2026_payroll_parameters_from_sqlite(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        payroll = load_payroll_tax_parameters(connection, 2026)

    assert payroll.social_security_rate == Decimal("0.062")
    assert payroll.social_security_wage_base == Decimal("184500.00")
    assert payroll.medicare_rate == Decimal("0.0145")
    assert payroll.additional_medicare_rate == Decimal("0.009")
    assert payroll.additional_medicare_threshold_single == Decimal("200000.00")
    assert payroll.additional_medicare_thresholds == {
        "single": Decimal("200000.00"),
        "married_joint": Decimal("250000.00"),
        "married_separate": Decimal("125000.00"),
        "head_of_household": Decimal("200000.00"),
    }


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("social_security_rate", "-0.10"),
        ("social_security_rate", "1.10"),
        ("social_security_wage_base", "-1.00"),
        ("social_security_wage_base", "-0.004"),
        ("medicare_rate", "-0.10"),
        ("medicare_rate", "1.10"),
        ("additional_medicare_rate", "-0.10"),
        ("additional_medicare_rate", "1.10"),
        ("additional_medicare_threshold_single", "-1.00"),
        ("additional_medicare_threshold_single", "-0.004"),
    ],
)
def test_rejects_invalid_payroll_parameters_from_sqlite(tmp_path, column, value):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        connection.execute(
            f"""
            UPDATE payroll_tax_parameters
            SET {column} = ?
            WHERE year = ?
            """,
            (value, 2026),
        )
        connection.commit()

        messages = {
            "social_security_rate": "social_security_rate must be between 0 and 1",
            "social_security_wage_base": (
                "social_security_wage_base must be non-negative"
            ),
            "medicare_rate": "medicare_rate must be between 0 and 1",
            "additional_medicare_rate": (
                "additional_medicare_rate must be between 0 and 1"
            ),
            "additional_medicare_threshold_single": (
                "additional_medicare_threshold_single must be non-negative"
            ),
        }
        with pytest.raises(ValueError, match=messages[column]):
            load_payroll_tax_parameters(connection, 2026)


@pytest.mark.parametrize("threshold", ["-1.00", "-0.004"])
def test_rejects_invalid_additional_medicare_thresholds_from_sqlite(
    tmp_path,
    threshold,
):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        connection.execute(
            """
            UPDATE additional_medicare_thresholds
            SET threshold = ?
            WHERE year = ? AND filing_status = ?
            """,
            (threshold, 2026, "single"),
        )
        connection.commit()

        with pytest.raises(
            ValueError, match="additional_medicare_threshold must be non-negative"
        ):
            load_payroll_tax_parameters(connection, 2026)


def test_loads_2026_pretax_deduction_parameters_from_sqlite(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        pretax = load_pretax_deduction_parameters(connection, 2026)

    assert pretax.tax_year == 2026
    assert pretax.employee_401k_limit == Decimal("24500.00")
    assert pretax.health_fsa_limit == Decimal("3400.00")
    assert pretax.dependent_care_fsa_limit == Decimal("7500.00")
    assert pretax.gradual_phase_in_start_rate == Decimal("0.01")


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("employee_401k_limit", "-1.00"),
        ("employee_401k_limit", "-0.004"),
        ("health_fsa_limit", "-1.00"),
        ("health_fsa_limit", "-0.004"),
        ("dependent_care_fsa_limit", "-1.00"),
        ("dependent_care_fsa_limit", "-0.004"),
        ("gradual_phase_in_start_rate", "-0.10"),
        ("gradual_phase_in_start_rate", "1.10"),
    ],
)
def test_rejects_invalid_pretax_deduction_parameters_from_sqlite(
    tmp_path,
    column,
    value,
):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        connection.execute(
            f"""
            UPDATE pretax_deduction_parameters
            SET {column} = ?
            WHERE year = ?
            """,
            (value, 2026),
        )
        connection.commit()

        messages = {
            "employee_401k_limit": "employee_401k_limit must be non-negative",
            "health_fsa_limit": "health_fsa_limit must be non-negative",
            "dependent_care_fsa_limit": (
                "dependent_care_fsa_limit must be non-negative"
            ),
            "gradual_phase_in_start_rate": (
                "gradual_phase_in_start_rate must be between 0 and 1"
            ),
        }
        with pytest.raises(ValueError, match=messages[column]):
            load_pretax_deduction_parameters(connection, 2026)


def test_additional_medicare_threshold_depends_on_filing_status(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        payroll = load_payroll_tax_parameters(connection, 2026)
        married_joint = load_federal_tax_parameters(connection, 2026, "married_joint")
        married_separate = load_federal_tax_parameters(
            connection, 2026, "married_separate"
        )

    joint_result = calculate_tax_burden(
        TaxScenario(gross_income=Decimal("225000")),
        federal=married_joint,
        payroll=payroll,
    )
    separate_result = calculate_tax_burden(
        TaxScenario(gross_income=Decimal("150000")),
        federal=married_separate,
        payroll=payroll,
    )

    assert joint_result.employee_additional_medicare_tax == Decimal("0.00")
    assert separate_result.employee_additional_medicare_tax == Decimal("194.40")


def test_seed_default_tax_data_preserves_existing_parameter_edits(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    initialize_database(db_path).close()
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE federal_tax_parameters
            SET standard_deduction = ?
            WHERE year = ? AND filing_status = ?
            """,
            ("17000.00", 2026, "single"),
        )
        connection.commit()

    with initialize_database(db_path) as connection:
        federal = load_federal_tax_parameters(connection, 2026, "single")

    assert federal.standard_deduction == Decimal("17000.00")


def test_seed_updates_legacy_pretax_dependent_care_limit(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    initialize_database(db_path).close()
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE pretax_deduction_parameters
            SET employee_401k_limit = ?, dependent_care_fsa_limit = ?
            WHERE year = ?
            """,
            ("25000.00", "0.00", 2026),
        )
        connection.commit()

    with initialize_database(db_path) as connection:
        pretax = load_pretax_deduction_parameters(connection, 2026)

    assert pretax.employee_401k_limit == Decimal("25000.00")
    assert pretax.dependent_care_fsa_limit == Decimal("7500.00")


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

    assert result.taxable_income == Decimal("56000.00")
    assert result.total_employee_tax == Decimal("14421.90")


def test_database_loaded_parameters_apply_dependent_care_fsa(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        federal = load_federal_tax_parameters(connection, 2026, "married_separate")
        payroll = load_payroll_tax_parameters(connection, 2026)
        pretax = load_pretax_deduction_parameters(connection, 2026)

    result = calculate_tax_burden(
        TaxScenario(gross_income=Decimal("100000"), dependent_count=1),
        federal=federal,
        payroll=payroll,
        pretax_deductions=pretax,
    )

    assert result.dependent_care_fsa_contribution == Decimal("3750.00")
    assert result.total_pretax_deductions == Decimal("31650.00")
    assert result.taxable_income == Decimal("52250.00")
    assert result.total_employee_tax == Decimal("13310.03")


def test_married_joint_secondary_income_uses_per_worker_social_security_caps(
    tmp_path,
):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        federal = load_federal_tax_parameters(connection, 2026, "married_joint")
        payroll = load_payroll_tax_parameters(connection, 2026)
        pretax = load_pretax_deduction_parameters(connection, 2026)

    result = calculate_tax_burden(
        TaxScenario(
            gross_income=Decimal("300000"),
            secondary_income=Decimal("150000"),
        ),
        federal=federal,
        payroll=payroll,
        pretax_deductions=pretax,
    )

    assert result.employee_401k_contribution == Decimal("49000.00")
    assert result.health_fsa_contribution == Decimal("6800.00")
    assert result.dependent_care_fsa_contribution == Decimal("0.00")
    assert result.total_pretax_deductions == Decimal("55800.00")
    assert result.taxable_income == Decimal("212000.00")
    assert result.federal_income_tax == Decimal("36076.00")
    assert result.employee_social_security_tax == Decimal("18178.40")
    assert result.employee_medicare_tax == Decimal("4251.40")
    assert result.employee_additional_medicare_tax == Decimal("388.80")
    assert result.total_employee_tax == Decimal("58894.60")


def test_married_joint_secondary_income_extends_gradual_deduction_phase_in(
    tmp_path,
):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        federal = load_federal_tax_parameters(connection, 2026, "married_joint")
        payroll = load_payroll_tax_parameters(connection, 2026)
        pretax = load_pretax_deduction_parameters(connection, 2026)

    old_dual_cap_endpoint = calculate_tax_burden(
        TaxScenario(
            gross_income=Decimal("600450"),
            secondary_income=Decimal("300225"),
            pretax_deduction_mode="gradual_phase_in",
        ),
        federal=federal,
        payroll=payroll,
        pretax_deductions=pretax,
    )
    extended_endpoint = calculate_tax_burden(
        TaxScenario(
            gross_income=Decimal("858825"),
            secondary_income=Decimal("429412.50"),
            pretax_deduction_mode="gradual_phase_in",
        ),
        federal=federal,
        payroll=payroll,
        pretax_deductions=pretax,
    )

    assert old_dual_cap_endpoint.total_pretax_deductions < Decimal("55800.00")
    assert extended_endpoint.employee_401k_contribution == Decimal("49000.00")
    assert extended_endpoint.health_fsa_contribution == Decimal("6800.00")
    assert extended_endpoint.total_pretax_deductions == Decimal("55800.00")


def test_secondary_income_requires_married_joint_filing_status(tmp_path):
    db_path = tmp_path / "tax.sqlite3"

    with initialize_database(db_path) as connection:
        federal = load_federal_tax_parameters(connection, 2026, "single")
        payroll = load_payroll_tax_parameters(connection, 2026)
        pretax = load_pretax_deduction_parameters(connection, 2026)

    with pytest.raises(ValueError, match="secondary_income"):
        calculate_tax_burden(
            TaxScenario(
                gross_income=Decimal("100000"),
                secondary_income=Decimal("25000"),
            ),
            federal=federal,
            payroll=payroll,
            pretax_deductions=pretax,
        )
