from __future__ import annotations

import os
import sqlite3
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from itertools import pairwise
from pathlib import Path

from tax_explorer import (
    FILING_STATUS_CHOICES,
    FILING_STATUSES,
    FederalTaxParameters,
    MONEY,
    PayrollTaxParameters,
    PretaxDeductionParameters,
    TaxBracket,
)


DEFAULT_DATABASE_PATH = Path(
    os.environ.get("TAX_EXPLORER_DB", Path.cwd() / "data" / "tax_explorer.sqlite3")
)
SQLITE_INTEGER_MAX = (1 << 63) - 1
_SUPPORTED_FILING_STATUS_SQL = ", ".join(
    f"'{filing_status}'" for filing_status in FILING_STATUS_CHOICES
)
_ECMASCRIPT_TRIM_CHARACTERS = (
    "\u0009\u000b\u000c\u0020\u00a0\ufeff\u000a\u000d\u2028\u2029"
    "\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009"
    "\u200a\u202f\u205f\u3000"
)

_AVAILABLE_TAX_YEAR_CTES = """
advertised_federal_statuses AS (
    SELECT
        federal.year,
        federal.filing_status,
        federal.standard_deduction,
        statuses.label AS filing_status_label
    FROM federal_tax_parameters AS federal
    LEFT JOIN filing_statuses AS statuses
        ON statuses.code = federal.filing_status
    WHERE federal.filing_status IN ({supported_filing_statuses})
),
bracketed_federal_statuses AS (
    SELECT federal.year, federal.filing_status
    FROM advertised_federal_statuses AS federal
    WHERE EXISTS (
          SELECT 1
          FROM federal_tax_brackets AS bracket
          WHERE bracket.year = federal.year
            AND bracket.filing_status = federal.filing_status
            AND tax_explorer_money_cents(bracket.lower_bound) IS NOT NULL
            AND tax_explorer_money_cents(bracket.lower_bound) = '0'
            AND tax_explorer_rate_valid(bracket.rate)
      )
)
""".format(supported_filing_statuses=_SUPPORTED_FILING_STATUS_SQL)

_AVAILABLE_TAX_YEAR_PREDICATE = """
years.year >= 0
  AND EXISTS (
    SELECT 1
    FROM bracketed_federal_statuses AS federal
    WHERE federal.year = years.year
)
  AND NOT EXISTS (
      SELECT 1
      FROM advertised_federal_statuses AS federal
      WHERE federal.year = years.year
        AND NOT tax_explorer_non_blank_string(federal.filing_status_label)
  )
  AND NOT EXISTS (
      SELECT 1
      FROM advertised_federal_statuses AS federal
      WHERE federal.year = years.year
        AND tax_explorer_money_cents(federal.standard_deduction) IS NULL
  )
  AND NOT EXISTS (
      SELECT 1
      FROM advertised_federal_statuses AS federal
      INNER JOIN federal_tax_brackets AS bracket
          ON bracket.year = federal.year
         AND bracket.filing_status = federal.filing_status
      WHERE federal.year = years.year
        AND (
            tax_explorer_money_cents(bracket.lower_bound) IS NULL
            OR NOT tax_explorer_rate_valid(bracket.rate)
        )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM advertised_federal_statuses AS federal
      INNER JOIN federal_tax_brackets AS bracket
          ON bracket.year = federal.year
         AND bracket.filing_status = federal.filing_status
      WHERE federal.year = years.year
      GROUP BY
          federal.year,
          federal.filing_status,
          tax_explorer_money_cents(bracket.lower_bound)
      HAVING COUNT(*) > 1
  )
  AND NOT EXISTS (
      SELECT 1
      FROM advertised_federal_statuses AS federal
      WHERE federal.year = years.year
        AND NOT EXISTS (
            SELECT 1
            FROM bracketed_federal_statuses AS bracketed
            WHERE bracketed.year = federal.year
              AND bracketed.filing_status = federal.filing_status
        )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM advertised_federal_statuses AS federal
      WHERE federal.year = years.year
        AND NOT EXISTS (
            SELECT 1
            FROM additional_medicare_thresholds AS threshold
            WHERE threshold.year = federal.year
              AND threshold.filing_status = federal.filing_status
        )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM advertised_federal_statuses AS federal
      INNER JOIN additional_medicare_thresholds AS threshold
          ON threshold.year = federal.year
         AND threshold.filing_status = federal.filing_status
      WHERE federal.year = years.year
        AND tax_explorer_money_cents(threshold.threshold) IS NULL
  )
  AND NOT EXISTS (
      SELECT 1
      FROM payroll_tax_parameters AS payroll
      INNER JOIN additional_medicare_thresholds AS threshold
          ON threshold.year = payroll.year
         AND threshold.filing_status = 'single'
      WHERE payroll.year = years.year
        AND tax_explorer_money_cents(threshold.threshold)
            IS NOT tax_explorer_money_cents(
                payroll.additional_medicare_threshold_single
            )
  )
  AND EXISTS (
      SELECT 1
      FROM payroll_tax_parameters AS payroll
      WHERE payroll.year = years.year
        AND tax_explorer_rate_valid(payroll.social_security_rate)
        AND tax_explorer_money_cents(payroll.social_security_wage_base)
            IS NOT NULL
        AND tax_explorer_rate_valid(payroll.medicare_rate)
        AND tax_explorer_rate_valid(payroll.additional_medicare_rate)
        AND tax_explorer_money_cents(
            payroll.additional_medicare_threshold_single
        ) IS NOT NULL
  )
  AND EXISTS (
      SELECT 1
      FROM pretax_deduction_parameters AS pretax
      WHERE pretax.year = years.year
        AND tax_explorer_money_cents(pretax.employee_401k_limit) IS NOT NULL
        AND tax_explorer_money_cents(pretax.health_fsa_limit) IS NOT NULL
        AND tax_explorer_money_cents(pretax.dependent_care_fsa_limit) IS NOT NULL
        AND tax_explorer_rate_valid(pretax.gradual_phase_in_start_rate)
  )
"""


def connect(database_path: str | Path = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    connection.create_function(
        "tax_explorer_money_cents", 1, _money_cents_for_sql, deterministic=True
    )
    connection.create_function(
        "tax_explorer_rate_valid", 1, _rate_valid_for_sql, deterministic=True
    )
    connection.create_function(
        "tax_explorer_non_blank_string",
        1,
        _non_blank_string_for_sql,
        deterministic=True,
    )
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
    rows = connection.execute(
        f"""
        WITH {_AVAILABLE_TAX_YEAR_CTES}
        SELECT years.year
        FROM tax_years AS years
        WHERE {_AVAILABLE_TAX_YEAR_PREDICATE}
        ORDER BY years.year
        """
    ).fetchall()
    return [int(row["year"]) for row in rows]


def is_tax_year_available(connection: sqlite3.Connection, year: int) -> bool:
    row = connection.execute(
        f"""
        WITH {_AVAILABLE_TAX_YEAR_CTES}
        SELECT 1
        FROM tax_years AS years
        WHERE years.year = ?
          AND {_AVAILABLE_TAX_YEAR_PREDICATE}
        LIMIT 1
        """,
        (year,),
    ).fetchone()
    return row is not None


def get_filing_statuses(
    connection: sqlite3.Connection, year: int
) -> list[dict[str, str]]:
    rows = connection.execute(
        f"""
        SELECT statuses.code, statuses.label, statuses.sort_order
        FROM filing_statuses AS statuses
        INNER JOIN federal_tax_parameters AS federal
            ON federal.filing_status = statuses.code
        WHERE federal.year = ?
          AND statuses.code IN ({_SUPPORTED_FILING_STATUS_SQL})
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
    if str(parameter_row["filing_status"]) not in FILING_STATUSES:
        raise ValueError(f"unsupported filing_status: {parameter_row['filing_status']}")

    bracket_rows = connection.execute(
        """
        SELECT lower_bound, rate
        FROM federal_tax_brackets
        WHERE year = ? AND filing_status = ?
        """,
        (year, filing_status),
    ).fetchall()
    if not bracket_rows:
        raise ValueError(f"No federal tax brackets for {year} {filing_status}")

    brackets = tuple(
        sorted(
            (
                TaxBracket(
                    lower_bound=_non_negative_money(
                        row["lower_bound"], "bracket lower_bound"
                    ),
                    rate=_rate(row["rate"], "bracket rate"),
                )
                for row in bracket_rows
            ),
            key=lambda bracket: bracket.lower_bound,
        )
    )
    _validate_federal_tax_brackets(brackets)

    return FederalTaxParameters(
        tax_year=int(parameter_row["year"]),
        filing_status=str(parameter_row["filing_status"]),
        standard_deduction=_non_negative_money(
            parameter_row["standard_deduction"], "standard_deduction"
        ),
        brackets=brackets,
    )


def _validate_federal_tax_brackets(brackets: tuple[TaxBracket, ...]) -> None:
    if brackets[0].lower_bound != Decimal("0.00"):
        raise ValueError("federal tax brackets must start at 0.00")

    for previous_bracket, bracket in pairwise(brackets):
        if bracket.lower_bound <= previous_bracket.lower_bound:
            raise ValueError("federal tax bracket lower_bounds must increase")


def _non_negative_money(value: object, field_name: str) -> Decimal:
    amount = _finite_decimal(value, field_name)
    if amount < 0:
        raise ValueError(f"{field_name} must be non-negative")
    try:
        return amount.quantize(MONEY, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError(f"{field_name} must fit cents precision") from None


def _money_cents_for_sql(value: object) -> str | None:
    try:
        amount = _non_negative_money(value, "money")
    except ValueError:
        return None
    return str(int(amount * 100))


def _rate_valid_for_sql(value: object) -> bool:
    try:
        _rate(value, "rate")
    except ValueError:
        return False
    return True


def _non_blank_string_for_sql(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip(_ECMASCRIPT_TRIM_CHARACTERS))


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
    supported_filing_statuses = [
        status["code"] for status in get_filing_statuses(connection, year)
    ]
    threshold_validation_statuses = set(supported_filing_statuses)
    threshold_validation_statuses.add("single")
    supported_thresholds_by_status = {}
    for threshold_row in threshold_rows:
        filing_status = str(threshold_row["filing_status"])
        if filing_status not in threshold_validation_statuses:
            continue
        supported_thresholds_by_status[filing_status] = _non_negative_money(
            threshold_row["threshold"], "additional_medicare_threshold"
        )
    additional_medicare_thresholds = {}
    for filing_status in supported_filing_statuses:
        if filing_status not in supported_thresholds_by_status:
            raise ValueError(
                f"additional_medicare_threshold missing for {year} {filing_status}"
            )
        additional_medicare_thresholds[filing_status] = supported_thresholds_by_status[
            filing_status
        ]
    additional_medicare_threshold_single = _non_negative_money(
        row["additional_medicare_threshold_single"],
        "additional_medicare_threshold_single",
    )
    stored_single_threshold = supported_thresholds_by_status.get("single")
    if (
        stored_single_threshold is not None
        and stored_single_threshold != additional_medicare_threshold_single
    ):
        raise ValueError(
            "additional_medicare_threshold_single "
            f"{additional_medicare_threshold_single} does not match "
            f"additional_medicare_threshold for {year} single"
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
