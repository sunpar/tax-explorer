from __future__ import annotations

import os
import sqlite3
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from tax_explorer import (
    FederalTaxParameters,
    MONEY,
    PayrollTaxParameters,
    PretaxDeductionParameters,
    TaxBracket,
)


DEFAULT_DATABASE_PATH = Path(
    os.environ.get("TAX_EXPLORER_DB", Path.cwd() / "data" / "tax_explorer.sqlite3")
)


def connect(database_path: str | Path = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> sqlite3.Connection:
    connection = connect(database_path)
    create_schema(connection)
    seed_default_tax_data(connection)
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tax_years (
            year INTEGER PRIMARY KEY,
            label TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS filing_statuses (
            code TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            sort_order INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS federal_tax_parameters (
            year INTEGER NOT NULL,
            filing_status TEXT NOT NULL,
            standard_deduction TEXT NOT NULL,
            PRIMARY KEY (year, filing_status),
            FOREIGN KEY (year) REFERENCES tax_years(year),
            FOREIGN KEY (filing_status) REFERENCES filing_statuses(code)
        );

        CREATE TABLE IF NOT EXISTS federal_tax_brackets (
            year INTEGER NOT NULL,
            filing_status TEXT NOT NULL,
            lower_bound TEXT NOT NULL,
            rate TEXT NOT NULL,
            PRIMARY KEY (year, filing_status, lower_bound),
            FOREIGN KEY (year, filing_status)
                REFERENCES federal_tax_parameters(year, filing_status)
        );

        CREATE TABLE IF NOT EXISTS payroll_tax_parameters (
            year INTEGER PRIMARY KEY,
            social_security_rate TEXT NOT NULL,
            social_security_wage_base TEXT NOT NULL,
            medicare_rate TEXT NOT NULL,
            additional_medicare_rate TEXT NOT NULL,
            additional_medicare_threshold_single TEXT NOT NULL,
            FOREIGN KEY (year) REFERENCES tax_years(year)
        );

        CREATE TABLE IF NOT EXISTS additional_medicare_thresholds (
            year INTEGER NOT NULL,
            filing_status TEXT NOT NULL,
            threshold TEXT NOT NULL,
            PRIMARY KEY (year, filing_status),
            FOREIGN KEY (year) REFERENCES tax_years(year),
            FOREIGN KEY (filing_status) REFERENCES filing_statuses(code)
        );

        CREATE TABLE IF NOT EXISTS pretax_deduction_parameters (
            year INTEGER PRIMARY KEY,
            employee_401k_limit TEXT NOT NULL,
            health_fsa_limit TEXT NOT NULL,
            dependent_care_fsa_limit TEXT NOT NULL,
            gradual_phase_in_start_rate TEXT NOT NULL,
            FOREIGN KEY (year) REFERENCES tax_years(year)
        );
        """
    )
    connection.commit()


def seed_default_tax_data(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO tax_years (year, label)
        VALUES (?, ?)
        ON CONFLICT(year) DO NOTHING
        """,
        (2026, "Tax Year 2026"),
    )
    connection.executemany(
        """
        INSERT INTO filing_statuses (code, label, sort_order)
        VALUES (?, ?, ?)
        ON CONFLICT(code) DO NOTHING
        """,
        [
            ("single", "Single", 1),
            ("married_joint", "Married filing jointly", 2),
            ("married_separate", "Married filing separately", 3),
            ("head_of_household", "Head of household", 4),
        ],
    )
    connection.executemany(
        """
        INSERT INTO federal_tax_parameters (year, filing_status, standard_deduction)
        VALUES (?, ?, ?)
        ON CONFLICT(year, filing_status) DO NOTHING
        """,
        [
            (2026, "single", "16100.00"),
            (2026, "married_joint", "32200.00"),
            (2026, "married_separate", "16100.00"),
            (2026, "head_of_household", "24150.00"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO federal_tax_brackets (year, filing_status, lower_bound, rate)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(year, filing_status, lower_bound) DO NOTHING
        """,
        [
            (2026, "single", "0.00", "0.10"),
            (2026, "single", "12400.00", "0.12"),
            (2026, "single", "50400.00", "0.22"),
            (2026, "single", "105700.00", "0.24"),
            (2026, "single", "201775.00", "0.32"),
            (2026, "single", "256225.00", "0.35"),
            (2026, "single", "640600.00", "0.37"),
            (2026, "married_joint", "0.00", "0.10"),
            (2026, "married_joint", "24800.00", "0.12"),
            (2026, "married_joint", "100800.00", "0.22"),
            (2026, "married_joint", "211400.00", "0.24"),
            (2026, "married_joint", "403550.00", "0.32"),
            (2026, "married_joint", "512450.00", "0.35"),
            (2026, "married_joint", "768700.00", "0.37"),
            (2026, "married_separate", "0.00", "0.10"),
            (2026, "married_separate", "12400.00", "0.12"),
            (2026, "married_separate", "50400.00", "0.22"),
            (2026, "married_separate", "105700.00", "0.24"),
            (2026, "married_separate", "201775.00", "0.32"),
            (2026, "married_separate", "256225.00", "0.35"),
            (2026, "married_separate", "384350.00", "0.37"),
            (2026, "head_of_household", "0.00", "0.10"),
            (2026, "head_of_household", "17700.00", "0.12"),
            (2026, "head_of_household", "67450.00", "0.22"),
            (2026, "head_of_household", "105700.00", "0.24"),
            (2026, "head_of_household", "201750.00", "0.32"),
            (2026, "head_of_household", "256200.00", "0.35"),
            (2026, "head_of_household", "640600.00", "0.37"),
        ],
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
        ON CONFLICT(year) DO NOTHING
        """,
        (2026, "0.062", "184500.00", "0.0145", "0.009", "200000.00"),
    )
    connection.executemany(
        """
        INSERT INTO additional_medicare_thresholds (year, filing_status, threshold)
        VALUES (?, ?, ?)
        ON CONFLICT(year, filing_status) DO NOTHING
        """,
        [
            (2026, "single", "200000.00"),
            (2026, "married_joint", "250000.00"),
            (2026, "married_separate", "125000.00"),
            (2026, "head_of_household", "200000.00"),
        ],
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
        ON CONFLICT(year) DO NOTHING
        """,
        (2026, "24500.00", "3400.00", "7500.00", "0.01"),
    )
    connection.execute(
        """
        UPDATE pretax_deduction_parameters
        SET dependent_care_fsa_limit = ?
        WHERE year = ? AND dependent_care_fsa_limit = ?
        """,
        ("7500.00", 2026, "0.00"),
    )
    connection.commit()


def get_available_tax_years(connection: sqlite3.Connection) -> list[int]:
    rows = connection.execute("SELECT year FROM tax_years ORDER BY year").fetchall()
    return [int(row["year"]) for row in rows]


def get_filing_statuses(
    connection: sqlite3.Connection, year: int
) -> list[dict[str, str]]:
    rows = connection.execute(
        """
        SELECT DISTINCT statuses.code, statuses.label, statuses.sort_order
        FROM filing_statuses AS statuses
        INNER JOIN federal_tax_parameters AS federal
            ON federal.filing_status = statuses.code
        WHERE federal.year = ?
        ORDER BY statuses.sort_order
        """,
        (year,),
    ).fetchall()
    return [{"code": str(row["code"]), "label": str(row["label"])} for row in rows]


def load_federal_tax_parameters(
    connection: sqlite3.Connection, year: int, filing_status: str = "single"
) -> FederalTaxParameters:
    parameter_row = connection.execute(
        """
        SELECT year, filing_status, standard_deduction
        FROM federal_tax_parameters
        WHERE year = ? AND filing_status = ?
        """,
        (year, filing_status),
    ).fetchone()
    if parameter_row is None:
        raise ValueError(f"No federal tax parameters for {year} {filing_status}")

    bracket_rows = connection.execute(
        """
        SELECT lower_bound, rate
        FROM federal_tax_brackets
        WHERE year = ? AND filing_status = ?
        ORDER BY CAST(lower_bound AS REAL)
        """,
        (year, filing_status),
    ).fetchall()
    if not bracket_rows:
        raise ValueError(f"No federal tax brackets for {year} {filing_status}")

    brackets = tuple(
        TaxBracket(
            lower_bound=_non_negative_money(row["lower_bound"], "bracket lower_bound"),
            rate=_rate(row["rate"], "bracket rate"),
        )
        for row in bracket_rows
    )
    if brackets[0].lower_bound != Decimal("0.00"):
        raise ValueError("federal tax brackets must start at 0.00")

    return FederalTaxParameters(
        tax_year=int(parameter_row["year"]),
        filing_status=str(parameter_row["filing_status"]),
        standard_deduction=_non_negative_money(
            parameter_row["standard_deduction"], "standard_deduction"
        ),
        brackets=brackets,
    )


def _non_negative_money(value: object, field_name: str) -> Decimal:
    amount = _finite_decimal(value, field_name)
    if amount < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return amount.quantize(MONEY, rounding=ROUND_HALF_UP)


def _rate(value: object, field_name: str) -> Decimal:
    rate = _finite_decimal(value, field_name)
    if rate < 0 or rate > 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return rate


def _finite_decimal(value: object, field_name: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{field_name} must be a finite decimal") from None
    if not amount.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    return amount


def load_payroll_tax_parameters(
    connection: sqlite3.Connection, year: int
) -> PayrollTaxParameters:
    row = connection.execute(
        """
        SELECT
            year,
            social_security_rate,
            social_security_wage_base,
            medicare_rate,
            additional_medicare_rate,
            additional_medicare_threshold_single
        FROM payroll_tax_parameters
        WHERE year = ?
        """,
        (year,),
    ).fetchone()
    if row is None:
        raise ValueError(f"No payroll tax parameters for {year}")

    threshold_rows = connection.execute(
        """
        SELECT filing_status, threshold
        FROM additional_medicare_thresholds
        WHERE year = ?
        """,
        (year,),
    ).fetchall()
    additional_medicare_thresholds = {
        str(threshold_row["filing_status"]): _non_negative_money(
            threshold_row["threshold"], "additional_medicare_threshold"
        )
        for threshold_row in threshold_rows
    }
    additional_medicare_threshold_single = _non_negative_money(
        row["additional_medicare_threshold_single"],
        "additional_medicare_threshold_single",
    )
    additional_medicare_thresholds.setdefault(
        "single",
        additional_medicare_threshold_single,
    )

    return PayrollTaxParameters(
        tax_year=int(row["year"]),
        social_security_rate=_rate(
            row["social_security_rate"], "social_security_rate"
        ),
        social_security_wage_base=_non_negative_money(
            row["social_security_wage_base"], "social_security_wage_base"
        ),
        medicare_rate=_rate(row["medicare_rate"], "medicare_rate"),
        additional_medicare_rate=_rate(
            row["additional_medicare_rate"], "additional_medicare_rate"
        ),
        additional_medicare_threshold_single=additional_medicare_threshold_single,
        additional_medicare_thresholds=additional_medicare_thresholds,
    )


def load_pretax_deduction_parameters(
    connection: sqlite3.Connection, year: int
) -> PretaxDeductionParameters:
    row = connection.execute(
        """
        SELECT
            year,
            employee_401k_limit,
            health_fsa_limit,
            dependent_care_fsa_limit,
            gradual_phase_in_start_rate
        FROM pretax_deduction_parameters
        WHERE year = ?
        """,
        (year,),
    ).fetchone()
    if row is None:
        raise ValueError(f"No pre-tax deduction parameters for {year}")

    return PretaxDeductionParameters(
        tax_year=int(row["year"]),
        employee_401k_limit=_non_negative_money(
            row["employee_401k_limit"], "employee_401k_limit"
        ),
        health_fsa_limit=_non_negative_money(
            row["health_fsa_limit"], "health_fsa_limit"
        ),
        dependent_care_fsa_limit=_non_negative_money(
            row["dependent_care_fsa_limit"], "dependent_care_fsa_limit"
        ),
        gradual_phase_in_start_rate=_rate(
            row["gradual_phase_in_start_rate"], "gradual_phase_in_start_rate"
        ),
    )
