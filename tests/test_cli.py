import csv
import io

import pytest

from tax_explorer import TaxScenario, calculate_tax_burden
from tax_explorer.cli import CSV_FIELDS, main, write_csv
from tax_explorer.database import initialize_database


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
SQLITE_INTEGER_MAX = (1 << 63) - 1


def create_hidden_multi_status_year_database(database_path):
    with initialize_database(database_path) as connection:
        connection.execute(
            "INSERT INTO tax_years (year, label) VALUES (?, ?)",
            (2030, "Tax Year 2030"),
        )
        connection.executemany(
            """
            INSERT INTO federal_tax_parameters
                (year, filing_status, standard_deduction)
            VALUES (?, ?, ?)
            """,
            (
                (2030, "single", "17000.00"),
                (2030, "married_joint", "34000.00"),
            ),
        )
        connection.execute(
            """
            INSERT INTO federal_tax_brackets
                (year, filing_status, lower_bound, rate)
            VALUES (?, ?, ?, ?)
            """,
            (2030, "single", "0.00", "0.10"),
        )
        connection.execute(
            """
            INSERT INTO payroll_tax_parameters (
                year,
                social_security_rate,
                social_security_wage_base,
                medicare_rate,
                additional_medicare_rate,
                additional_medicare_threshold_single
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (2030, "0.062", "184500.00", "0.0145", "0.009", "200000.00"),
        )
        connection.executemany(
            """
            INSERT INTO additional_medicare_thresholds
                (year, filing_status, threshold)
            VALUES (?, ?, ?)
            """,
            (
                (2030, "single", "200000.00"),
                (2030, "married_joint", "250000.00"),
            ),
        )
        connection.execute(
            """
            INSERT INTO pretax_deduction_parameters (
                year,
                employee_401k_limit,
                health_fsa_limit,
                dependent_care_fsa_limit,
                gradual_phase_in_start_rate
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (2030, "24500.00", "3400.00", "7500.00", "0.01"),
        )
        connection.commit()


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


def test_cli_reports_sqlite_database_path_errors_without_a_traceback(
    tmp_path,
    capsys,
):
    with pytest.raises(SystemExit) as exc_info:
        main(["--stop", "0", "--database-path", str(tmp_path)])

    error = capsys.readouterr().err
    assert exc_info.value.code == 2
    assert "database error: unable to open database file" in error
    assert "Traceback" not in error


def test_cli_reports_database_parent_path_errors_without_a_traceback(
    tmp_path,
    capsys,
):
    parent_path = tmp_path / "not-a-directory"
    parent_path.write_text("")

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--stop",
                "0",
                "--database-path",
                str(parent_path / "tax.sqlite3"),
            ]
        )

    error = capsys.readouterr().err
    assert exc_info.value.code == 2
    assert "database error:" in error
    assert "Traceback" not in error


def test_cli_does_not_label_income_series_os_errors_as_database_errors(
    monkeypatch,
    tmp_path,
):
    downstream_error = OSError("downstream failure")

    def fail_to_build_income_series(**_kwargs):
        raise downstream_error

    monkeypatch.setattr(
        "tax_explorer.cli.build_income_series",
        fail_to_build_income_series,
    )

    with pytest.raises(OSError) as exc_info:
        main(["--stop", "0", "--database-path", str(tmp_path / "tax.sqlite3")])

    assert exc_info.value is downstream_error


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


def test_cli_excludes_tax_years_hidden_from_availability(tmp_path, capsys):
    database_path = tmp_path / "tax.sqlite3"
    create_hidden_multi_status_year_database(database_path)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--year",
                "2030",
                "--filing-status",
                "single",
                "--start",
                "100000",
                "--stop",
                "100000",
                "--step",
                "50000",
                "--database-path",
                str(database_path),
            ]
        )

    assert exc_info.value.code == 2
    assert "No tax parameters for 2030" in capsys.readouterr().err


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
        ("--start", "100_000"),
        ("--stop", "100_000"),
        ("--step", "10_000"),
        ("--secondary-income", "25_000"),
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
    database_path = tmp_path / "tax.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        main([flag, value, "--database-path", str(database_path)])

    assert exc_info.value.code == 2
    assert f"argument {flag}: must be a decimal number" in capsys.readouterr().err
    assert not database_path.exists()


@pytest.mark.parametrize(
    ("flag", "value", "message"),
    [
        ("--start", "-1", "must be non-negative"),
        ("--stop", "-1", "must be non-negative"),
        ("--step", "0", "must be positive"),
        ("--step", "-1", "must be positive"),
        ("--step", "0.004", "must be positive"),
        ("--step", "1e27", "must fit cents precision"),
        ("--secondary-income", "-1", "must be non-negative"),
        ("--dependent-count", "1.5", "must be a whole number"),
        ("--dependent-count", "1_0", "must be a whole number"),
        ("--year", "2026.5", "must be a whole number"),
        ("--year", "2_026", "must be a whole number"),
        ("--year", "-1", "must be non-negative"),
        (
            "--year",
            str(SQLITE_INTEGER_MAX + 1),
            f"must be at most {SQLITE_INTEGER_MAX}",
        ),
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


def test_cli_accepts_sqlite_maximum_year_through_argument_validation(
    tmp_path,
    capsys,
):
    database_path = tmp_path / "tax.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--year",
                str(SQLITE_INTEGER_MAX),
                "--database-path",
                str(database_path),
            ]
        )

    error = capsys.readouterr().err
    assert exc_info.value.code == 2
    assert f"No federal tax parameters for {SQLITE_INTEGER_MAX} single" in error
    assert f"must be at most {SQLITE_INTEGER_MAX}" not in error
    assert "Traceback" not in error
    assert database_path.exists()


def test_cli_preserves_integer_whitespace_syntax(tmp_path, capsys):
    code = main(
        [
            "--year",
            " 2026",
            "--dependent-count",
            "\t1",
            "--stop",
            "0",
            "--database-path",
            str(tmp_path / "tax.sqlite3"),
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.startswith("gross_income,")
    assert captured.err == ""


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


def test_cli_reports_unroundable_secondary_income_as_usage_error(
    tmp_path,
    capsys,
):
    database_path = tmp_path / "tax.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--secondary-income",
                "1e27",
                "--database-path",
                str(database_path),
            ]
        )

    assert exc_info.value.code == 2
    assert (
        "secondary_income is only supported for married_joint" in capsys.readouterr().err
    )
    assert not database_path.exists()


def test_cli_reports_unroundable_married_joint_secondary_income_before_stop_bound(
    tmp_path,
    capsys,
):
    database_path = tmp_path / "tax.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--filing-status",
                "married_joint",
                "--secondary-income",
                "1e27",
                "--database-path",
                str(database_path),
            ]
        )

    assert exc_info.value.code == 2
    assert (
        "argument --secondary-income: must fit cents precision"
        in capsys.readouterr().err
    )
    assert not database_path.exists()


def test_cli_reports_reversed_income_range_before_database_initialization(
    tmp_path,
    capsys,
):
    database_path = tmp_path / "tax.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--start",
                "100000",
                "--stop",
                "0",
                "--database-path",
                str(database_path),
            ]
        )

    assert exc_info.value.code == 2
    assert "start must be less than or equal to stop" in capsys.readouterr().err
    assert not database_path.exists()


def test_cli_reports_reversed_range_before_secondary_income_validation(
    tmp_path,
    capsys,
):
    database_path = tmp_path / "tax.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--start",
                "100000",
                "--stop",
                "0",
                "--secondary-income",
                "25000",
                "--database-path",
                str(database_path),
            ]
        )

    assert exc_info.value.code == 2
    assert "start must be less than or equal to stop" in capsys.readouterr().err
    assert not database_path.exists()


def test_cli_reports_unroundable_reversed_income_range_before_database_initialization(
    tmp_path,
    capsys,
):
    database_path = tmp_path / "tax.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--start",
                "1e999",
                "--stop",
                "0",
                "--database-path",
                str(database_path),
            ]
        )

    assert exc_info.value.code == 2
    assert "start must be less than or equal to stop" in capsys.readouterr().err
    assert not database_path.exists()


def test_cli_reports_unroundable_income_range_before_database_initialization(
    tmp_path,
    capsys,
):
    database_path = tmp_path / "tax.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--start",
                "1e27",
                "--stop",
                "1e27",
                "--database-path",
                str(database_path),
            ]
        )

    assert exc_info.value.code == 2
    assert "argument --start: must fit cents precision" in capsys.readouterr().err
    assert not database_path.exists()


def test_cli_compares_income_range_after_money_rounding(monkeypatch, tmp_path):
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    result = main(
        [
            "--start",
            "0.004",
            "--stop",
            "0.003",
            "--database-path",
            str(tmp_path / "tax.sqlite3"),
        ]
    )

    row = next(csv.DictReader(io.StringIO(output.getvalue())))
    assert result == 0
    assert row["gross_income"] == "0.00"


def test_cli_preserves_unsupported_year_error_for_unroundable_income_range(
    tmp_path,
    capsys,
):
    database_path = tmp_path / "tax.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--year",
                "9999",
                "--start",
                "1e999",
                "--stop",
                "1e999",
                "--database-path",
                str(database_path),
            ]
        )

    assert exc_info.value.code == 2
    assert "No federal tax parameters for 9999 single" in capsys.readouterr().err
    assert database_path.exists()


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
                "--stop",
                "100000",
                "--secondary-income",
                "1e27",
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
