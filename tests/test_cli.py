import csv
import io

import pytest

from tax_explorer import TaxScenario, calculate_tax_burden
from tax_explorer.cli import CSV_FIELDS, main, write_csv


LEGACY_CSV_FIELDS = (
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
)


def test_csv_export_preserves_existing_columns_and_appends_marginal_rates(
    monkeypatch,
):
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    write_csv([calculate_tax_burden(TaxScenario(gross_income="100000"))])

    assert CSV_FIELDS[: len(LEGACY_CSV_FIELDS)] == LEGACY_CSV_FIELDS
    assert CSV_FIELDS[len(LEGACY_CSV_FIELDS) :] == (
        "marginal_employee_tax_rate",
        "marginal_tax_rate_with_employer_payroll",
        "employee_401k_contribution",
        "health_fsa_contribution",
        "dependent_care_fsa_contribution",
        "total_pretax_deductions",
    )
    row = next(csv.DictReader(io.StringIO(output.getvalue())))
    assert row["marginal_employee_tax_rate"] == "0.2965"
    assert row["marginal_tax_rate_with_employer_payroll"] == "0.2965"
    assert row["employee_401k_contribution"] == "24500.00"
    assert row["health_fsa_contribution"] == "3400.00"
    assert row["dependent_care_fsa_contribution"] == "0.00"
    assert row["total_pretax_deductions"] == "27900.00"


def test_cli_accepts_gradual_pretax_deduction_mode(monkeypatch, tmp_path):
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    result = main(
        [
            "--start",
            "100000",
            "--stop",
            "100000",
            "--step",
            "50000",
            "--pretax-deduction-mode",
            "gradual_phase_in",
            "--database-path",
            str(tmp_path / "tax.sqlite3"),
        ]
    )

    row = next(csv.DictReader(io.StringIO(output.getvalue())))
    assert result == 0
    assert row["total_pretax_deductions"] == "3448.87"
    assert row["employee_401k_contribution"] == "3028.58"
    assert row["health_fsa_contribution"] == "420.29"


def test_cli_accepts_dependent_count(monkeypatch, tmp_path):
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    result = main(
        [
            "--start",
            "100000",
            "--stop",
            "100000",
            "--step",
            "50000",
            "--dependent-count",
            "1",
            "--database-path",
            str(tmp_path / "tax.sqlite3"),
        ]
    )

    row = next(csv.DictReader(io.StringIO(output.getvalue())))
    assert result == 0
    assert row["dependent_care_fsa_contribution"] == "7500.00"
    assert row["total_pretax_deductions"] == "35400.00"
    assert row["total_employee_tax"] == "12388.15"


def test_cli_rejects_negative_dependent_count():
    with pytest.raises(SystemExit) as exc_info:
        main(["--dependent-count", "-1"])

    assert exc_info.value.code == 2


def test_cli_rejects_unknown_pretax_deduction_mode():
    with pytest.raises(SystemExit) as exc_info:
        main(["--pretax-deduction-mode", "unknown"])

    assert exc_info.value.code == 2


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--start", "abc"),
        ("--stop", "abc"),
        ("--step", "abc"),
        ("--secondary-income", "abc"),
        ("--start", "NaN"),
        ("--stop", "Infinity"),
        ("--step", "Infinity"),
        ("--secondary-income", "NaN"),
    ],
)
def test_cli_reports_invalid_decimal_arguments_as_usage_errors(
    flag,
    value,
    tmp_path,
    capsys,
):
    with pytest.raises(SystemExit) as exc_info:
        main([flag, value, "--database-path", str(tmp_path / "tax.sqlite3")])

    assert exc_info.value.code == 2
    assert f"argument {flag}: must be a decimal number" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("flag", "value", "message"),
    [
        ("--start", "-1", "must be non-negative"),
        ("--stop", "-1", "must be non-negative"),
        ("--step", "0", "must be positive"),
        ("--step", "-1", "must be positive"),
        ("--step", "0.004", "must be positive"),
        ("--secondary-income", "-1", "must be non-negative"),
        ("--dependent-count", "1.5", "must be a whole number"),
        ("--year", "2026.5", "must be a whole number"),
        ("--year", "-1", "must be non-negative"),
    ],
)
def test_cli_rejects_invalid_numeric_bounds_before_database_initialization(
    flag,
    value,
    message,
    tmp_path,
    capsys,
):
    database_path = tmp_path / "tax.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        main([flag, value, "--database-path", str(database_path)])

    assert exc_info.value.code == 2
    assert f"argument {flag}: {message}" in capsys.readouterr().err
    assert not database_path.exists()


def test_cli_reports_invalid_secondary_income_as_usage_error(tmp_path, capsys):
    database_path = tmp_path / "tax.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--secondary-income",
                "1",
                "--database-path",
                str(database_path),
            ]
        )

    assert exc_info.value.code == 2
    assert (
        "secondary_income is only supported for married_joint" in capsys.readouterr().err
    )
    assert not database_path.exists()


def test_cli_reports_secondary_income_above_stop_as_usage_error(tmp_path, capsys):
    database_path = tmp_path / "tax.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--filing-status",
                "married_joint",
                "--stop",
                "100000",
                "--secondary-income",
                "120000",
                "--database-path",
                str(database_path),
            ]
        )

    assert exc_info.value.code == 2
    assert "secondary_income cannot exceed stop" in capsys.readouterr().err
    assert not database_path.exists()


def test_cli_preserves_unsupported_filing_status_error_with_secondary_income(
    tmp_path,
    capsys,
):
    database_path = tmp_path / "tax.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--filing-status",
                "unknown",
                "--secondary-income",
                "1",
                "--database-path",
                str(database_path),
            ]
        )

    assert exc_info.value.code == 2
    assert "No federal tax parameters for 2026 unknown" in capsys.readouterr().err
    assert database_path.exists()


def test_cli_compares_secondary_income_bounds_after_money_rounding(
    monkeypatch,
    tmp_path,
):
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    result = main(
        [
            "--filing-status",
            "married_joint",
            "--start",
            "100000.005",
            "--stop",
            "100000.005",
            "--step",
            "50000",
            "--secondary-income",
            "100000.006",
            "--database-path",
            str(tmp_path / "tax.sqlite3"),
        ]
    )

    row = next(csv.DictReader(io.StringIO(output.getvalue())))
    assert result == 0
    assert row["gross_income"] == "100000.01"


def test_cli_accepts_year_filing_status_and_secondary_income(monkeypatch, tmp_path):
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    result = main(
        [
            "--year",
            "2026",
            "--filing-status",
            "married_joint",
            "--start",
            "300000",
            "--stop",
            "300000",
            "--step",
            "50000",
            "--secondary-income",
            "150000",
            "--database-path",
            str(tmp_path / "tax.sqlite3"),
        ]
    )

    row = next(csv.DictReader(io.StringIO(output.getvalue())))
    assert result == 0
    assert row["employee_401k_contribution"] == "49000.00"
    assert row["health_fsa_contribution"] == "6800.00"
    assert row["total_pretax_deductions"] == "55800.00"
    assert row["employee_social_security_tax"] == "18178.40"


def test_cli_can_include_marginal_breakpoint_rows(monkeypatch, tmp_path):
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    result = main(
        [
            "--start",
            "0",
            "--stop",
            "100000",
            "--step",
            "100000",
            "--include-marginal-breakpoints",
            "--database-path",
            str(tmp_path / "tax.sqlite3"),
        ]
    )

    rows = list(csv.DictReader(io.StringIO(output.getvalue())))
    assert result == 0
    assert [row["gross_income"] for row in rows] == [
        "0.00",
        "27900.00",
        "44000.00",
        "56400.00",
        "94400.00",
        "100000.00",
    ]
