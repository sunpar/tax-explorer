from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from tax_explorer import (
    FederalTaxParameters,
    PayrollTaxParameters,
    TaxBurden,
    TaxScenario,
    build_income_series,
    calculate_tax_burden,
)
from tax_explorer.database import (
    DEFAULT_DATABASE_PATH,
    get_available_tax_years,
    get_filing_statuses,
    initialize_database,
    load_federal_tax_parameters,
    load_payroll_tax_parameters,
)


class CalculateRequest(BaseModel):
    year: int
    filing_status: str = "single"
    gross_income: Decimal = Field(ge=0)
    include_employer_payroll_tax: bool = False


def create_app(database_path: str | Path = DEFAULT_DATABASE_PATH) -> FastAPI:
    app = FastAPI(title="Tax Explorer API")
    app.state.database_path = Path(database_path)
    bootstrap = initialize_database(app.state.database_path)
    bootstrap.close()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/tax-years")
    def tax_years() -> dict[str, list[int]]:
        with _database(app) as connection:
            return {"years": get_available_tax_years(connection)}

    @app.get("/api/tax-years/{year}/filing-statuses")
    def filing_statuses(year: int) -> dict[str, list[dict[str, str]]]:
        with _database(app) as connection:
            statuses = get_filing_statuses(connection, year)
        if not statuses:
            raise HTTPException(
                status_code=404, detail=f"No filing statuses for {year}"
            )
        return {"statuses": statuses}

    @app.get("/api/tax-years/{year}/parameters")
    def tax_parameters(
        year: int, filing_status: str = Query(default="single")
    ) -> dict[str, Any]:
        try:
            with _database(app) as connection:
                federal = load_federal_tax_parameters(connection, year, filing_status)
                payroll = load_payroll_tax_parameters(connection, year)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return {
            "federal": _federal_to_response(federal),
            "payroll": _payroll_to_response(payroll),
        }

    @app.post("/api/calculate")
    def calculate(request: CalculateRequest) -> dict[str, str]:
        try:
            federal, payroll = _load_parameters(
                app, request.year, request.filing_status
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        result = calculate_tax_burden(
            TaxScenario(
                gross_income=request.gross_income,
                include_employer_payroll_tax=request.include_employer_payroll_tax,
            ),
            federal=federal,
            payroll=payroll,
        )
        return _tax_burden_to_response(result)

    @app.get("/api/income-series")
    def income_series(
        year: int,
        filing_status: str = Query(default="single"),
        start: Decimal = Query(default=Decimal("0"), ge=0),
        stop: Decimal = Query(default=Decimal("500000"), ge=0),
        step: Decimal = Query(default=Decimal("10000"), gt=0),
        include_employer_payroll_tax: bool = Query(default=False),
    ) -> dict[str, list[dict[str, str]]]:
        try:
            federal, payroll = _load_parameters(app, year, filing_status)
            rows = build_income_series(
                start=start,
                stop=stop,
                step=step,
                include_employer_payroll_tax=include_employer_payroll_tax,
                federal=federal,
                payroll=payroll,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return {"rows": [_tax_burden_to_response(row) for row in rows]}

    return app


@contextmanager
def _database(app: FastAPI) -> Iterator[Any]:
    connection = initialize_database(app.state.database_path)
    try:
        yield connection
    finally:
        connection.close()


def _load_parameters(
    app: FastAPI, year: int, filing_status: str
) -> tuple[FederalTaxParameters, PayrollTaxParameters]:
    with _database(app) as connection:
        federal = load_federal_tax_parameters(connection, year, filing_status)
        payroll = load_payroll_tax_parameters(connection, year)
    return federal, payroll


def _federal_to_response(parameters: FederalTaxParameters) -> dict[str, Any]:
    return {
        "tax_year": parameters.tax_year,
        "filing_status": parameters.filing_status,
        "standard_deduction": _decimal_to_string(parameters.standard_deduction),
        "brackets": [
            {
                "lower_bound": _decimal_to_string(bracket.lower_bound),
                "rate": _decimal_to_string(bracket.rate),
            }
            for bracket in parameters.brackets
        ],
    }


def _payroll_to_response(parameters: PayrollTaxParameters) -> dict[str, Any]:
    return {
        key: _decimal_to_string(value) if isinstance(value, Decimal) else value
        for key, value in asdict(parameters).items()
    }


def _tax_burden_to_response(result: TaxBurden) -> dict[str, str]:
    return {
        key: _decimal_to_string(value) if isinstance(value, Decimal) else str(value)
        for key, value in asdict(result).items()
    }


def _decimal_to_string(value: Decimal) -> str:
    return format(value, "f")


app = create_app()
