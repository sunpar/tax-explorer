from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from tax_explorer import (
    FederalTaxParameters,
    PayrollTaxParameters,
    TaxBracket,
    _money,
)
from decimal import Decimal


DEFAULT_DATABASE_PATH = Path(
    os.environ.get("TAX_EXPLORER_DB", Path.cwd() / "data" / "tax_explorer.sqlite3")
)


def connect(database_path: str | Path = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
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

        CREATE TABLE IF NOT EXISTS federal_tax_parameters (
            year INTEGER NOT NULL,
            filing_status TEXT NOT NULL,
            standard_deduction TEXT NOT NULL,
            PRIMARY KEY (year, filing_status),
            FOREIGN KEY (year) REFERENCES tax_years(year)
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
        """
    )
    connection.commit()


def seed_default_tax_data(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO tax_years (year, label)
        VALUES (?, ?)
        ON CONFLICT(year) DO UPDATE SET label = excluded.label
        """,
        (2026, "Tax Year 2026"),
    )
    connection.execute(
        """
        INSERT INTO federal_tax_parameters (year, filing_status, standard_deduction)
        VALUES (?, ?, ?)
        ON CONFLICT(year, filing_status) DO UPDATE
        SET standard_deduction = excluded.standard_deduction
        """,
        (2026, "single", "16100.00"),
    )
    connection.executemany(
        """
        INSERT INTO federal_tax_brackets (year, filing_status, lower_bound, rate)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(year, filing_status, lower_bound) DO UPDATE
        SET rate = excluded.rate
        """,
        [
            (2026, "single", "0.00", "0.10"),
            (2026, "single", "12400.00", "0.12"),
            (2026, "single", "50400.00", "0.22"),
            (2026, "single", "105700.00", "0.24"),
            (2026, "single", "201775.00", "0.32"),
            (2026, "single", "256225.00", "0.35"),
            (2026, "single", "640600.00", "0.37"),
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
        ON CONFLICT(year) DO UPDATE SET
            social_security_rate = excluded.social_security_rate,
            social_security_wage_base = excluded.social_security_wage_base,
            medicare_rate = excluded.medicare_rate,
            additional_medicare_rate = excluded.additional_medicare_rate,
            additional_medicare_threshold_single =
                excluded.additional_medicare_threshold_single
        """,
        (2026, "0.062", "184500.00", "0.0145", "0.009", "200000.00"),
    )
    connection.commit()


def get_available_tax_years(connection: sqlite3.Connection) -> list[int]:
    rows = connection.execute("SELECT year FROM tax_years ORDER BY year").fetchall()
    return [int(row["year"]) for row in rows]


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

    return FederalTaxParameters(
        tax_year=int(parameter_row["year"]),
        filing_status=str(parameter_row["filing_status"]),
        standard_deduction=_money(parameter_row["standard_deduction"]),
        brackets=tuple(
            TaxBracket(
                lower_bound=_money(row["lower_bound"]),
                rate=Decimal(str(row["rate"])),
            )
            for row in bracket_rows
        ),
    )


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

    return PayrollTaxParameters(
        tax_year=int(row["year"]),
        social_security_rate=Decimal(str(row["social_security_rate"])),
        social_security_wage_base=_money(row["social_security_wage_base"]),
        medicare_rate=Decimal(str(row["medicare_rate"])),
        additional_medicare_rate=Decimal(str(row["additional_medicare_rate"])),
        additional_medicare_threshold_single=_money(
            row["additional_medicare_threshold_single"]
        ),
    )
