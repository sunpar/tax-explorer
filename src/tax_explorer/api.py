from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from tax_explorer import (
    FederalTaxParameters,
    PayrollTaxParameters,
    PRETAX_DEDUCTION_MODE_GRADUAL_PHASE_IN,
    PRETAX_DEDUCTION_MODE_MAX_AVAILABLE,
    PretaxDeductionParameters,
    TaxBurden,
    TaxScenario,
    build_income_series,
    calculate_tax_burden,
)
from tax_explorer.database import (
    DEFAULT_DATABASE_PATH,
    connect,
    get_available_tax_years,
    get_filing_statuses,
    initialize_database,
    load_federal_tax_parameters,
    load_payroll_tax_parameters,
    load_pretax_deduction_parameters,
)


PretaxDeductionMode = Literal[
    PRETAX_DEDUCTION_MODE_MAX_AVAILABLE,
    PRETAX_DEDUCTION_MODE_GRADUAL_PHASE_IN,
]
MISSING_PARAMETER_MESSAGE_PREFIXES = (
    "No federal tax parameters",
    "No federal tax brackets",
    "No payroll tax parameters",
    "No pre-tax deduction parameters",
)


class CalculateRequest(BaseModel):
    year: int
    filing_status: str = "single"
    gross_income: Decimal = Field(ge=0)
    include_employer_payroll_tax: bool = False
    dependent_count: int = Field(default=0, ge=0)
    secondary_income: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    pretax_deduction_mode: PretaxDeductionMode = PRETAX_DEDUCTION_MODE_MAX_AVAILABLE

    @model_validator(mode="after")
    def validate_income_split(self) -> "CalculateRequest":
        if self.secondary_income > self.gross_income:
            raise ValueError("secondary_income cannot exceed gross_income")
        return self


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
                pretax = load_pretax_deduction_parameters(connection, year)
        except ValueError as exc:
            raise _parameter_http_exception(exc) from exc

        return {
            "federal": _federal_to_response(federal),
            "payroll": _dataclass_to_response(payroll),
            "pretax_deductions": _dataclass_to_response(pretax),
        }

    @app.post("/api/calculate")
    def calculate(request: CalculateRequest) -> dict[str, Any]:
        try:
            federal, payroll, pretax = _load_parameters(
                app, request.year, request.filing_status
            )
        except ValueError as exc:
            raise _parameter_http_exception(exc) from exc

        try:
            result = calculate_tax_burden(
                TaxScenario(
                    gross_income=request.gross_income,
                    include_employer_payroll_tax=request.include_employer_payroll_tax,
                    pretax_deduction_mode=request.pretax_deduction_mode,
                    dependent_count=request.dependent_count,
                    secondary_income=request.secondary_income,
                ),
                federal=federal,
                payroll=payroll,
                pretax_deductions=pretax,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _tax_burden_to_response(result)

    @app.get("/api/income-series")
    def income_series(
        year: int,
        filing_status: str = Query(default="single"),
        start: Decimal = Query(default=Decimal("0"), ge=0),
        stop: Decimal = Query(default=Decimal("500000"), ge=0),
        step: Decimal = Query(default=Decimal("10000"), gt=0),
        include_employer_payroll_tax: bool = Query(default=False),
        include_marginal_breakpoints: bool = Query(default=False),
        dependent_count: int = Query(default=0, ge=0),
        secondary_income: Decimal = Query(default=Decimal("0"), ge=0),
        pretax_deduction_mode: PretaxDeductionMode = Query(
            default=PRETAX_DEDUCTION_MODE_MAX_AVAILABLE
        ),
    ) -> dict[str, list[dict[str, Any]]]:
        try:
            federal, payroll, pretax = _load_parameters(app, year, filing_status)
        except ValueError as exc:
            raise _parameter_http_exception(exc) from exc

        try:
            rows = build_income_series(
                start=start,
                stop=stop,
                step=step,
                include_employer_payroll_tax=include_employer_payroll_tax,
                include_marginal_breakpoints=include_marginal_breakpoints,
                pretax_deduction_mode=pretax_deduction_mode,
                dependent_count=dependent_count,
                secondary_income=secondary_income,
                federal=federal,
                payroll=payroll,
                pretax_deductions=pretax,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return {"rows": [_tax_burden_to_response(row) for row in rows]}

    return app


@contextmanager
def _database(app: FastAPI) -> Iterator[Any]:
    connection = connect(app.state.database_path)
    try:
        yield connection
    finally:
        connection.close()


def _load_parameters(
    app: FastAPI, year: int, filing_status: str
) -> tuple[FederalTaxParameters, PayrollTaxParameters, PretaxDeductionParameters]:
    with _database(app) as connection:
        federal = load_federal_tax_parameters(connection, year, filing_status)
        payroll = load_payroll_tax_parameters(connection, year)
        pretax = load_pretax_deduction_parameters(connection, year)
    return federal, payroll, pretax


def _parameter_http_exception(exc: ValueError) -> HTTPException:
    detail = str(exc)
    status_code = 404 if _is_missing_parameter_error(detail) else 422
    return HTTPException(status_code=status_code, detail=detail)


def _is_missing_parameter_error(detail: str) -> bool:
    return detail.startswith(MISSING_PARAMETER_MESSAGE_PREFIXES)


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


def _dataclass_to_response(parameters: Any) -> dict[str, Any]:
    return {
        key: _value_to_response(value)
        for key, value in asdict(parameters).items()
    }


def _tax_burden_to_response(result: TaxBurden) -> dict[str, Any]:
    response = {
        key: _value_to_response(value)
        for key, value in asdict(result).items()
    }
    response["tax_breakdown"] = _tax_breakdown_to_response(result)
    return response


def _tax_breakdown_to_response(result: TaxBurden) -> list[dict[str, str]]:
    components = [
        ("federal_income_tax", "Federal income tax", result.federal_income_tax),
        (
            "employee_social_security_tax",
            "Social Security tax",
            result.employee_social_security_tax,
        ),
        ("employee_medicare_tax", "Medicare tax", result.employee_medicare_tax),
        (
            "employee_additional_medicare_tax",
            "Additional Medicare tax",
            result.employee_additional_medicare_tax,
        ),
    ]
    if result.total_employer_payroll_tax > Decimal("0"):
        components.extend(
            [
                (
                    "employer_social_security_tax",
                    "Employer Social Security tax",
                    result.employer_social_security_tax,
                ),
                (
                    "employer_medicare_tax",
                    "Employer Medicare tax",
                    result.employer_medicare_tax,
                ),
            ]
        )

    return [
        {"code": code, "label": label, "amount": _decimal_to_string(amount)}
        for code, label, amount in components
    ]


def _decimal_to_string(value: Decimal) -> str:
    return format(value, "f")


def _value_to_response(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_to_string(value)
    if isinstance(value, dict):
        return {
            key: _value_to_response(nested_value)
            for key, nested_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_value_to_response(nested_value) for nested_value in value]
    return value


app = create_app()
