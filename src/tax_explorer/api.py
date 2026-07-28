from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Annotated, Any, Iterator, Literal

from fastapi import FastAPI, HTTPException, Path as ApiPath, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, BeforeValidator, Field, model_validator

from tax_explorer import (
    FILING_STATUS_CHOICES,
    FederalTaxParameters,
    MONEY,
    PayrollTaxParameters,
    PRETAX_DEDUCTION_MODE_GRADUAL_PHASE_IN,
    PRETAX_DEDUCTION_MODE_MAX_AVAILABLE,
    PretaxDeductionParameters,
    TaxBurden,
    TaxScenario,
    calculate_income_series,
    calculate_tax_burden,
)
from tax_explorer.database import (
    DEFAULT_DATABASE_PATH,
    SQLITE_INTEGER_MAX,
    connect,
    get_available_tax_years,
    get_filing_statuses,
    initialize_database,
    is_tax_year_available,
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
    "No tax parameters",
)
DEFAULT_TAX_YEAR = 2026
_NON_NEGATIVE_INTEGER_SCHEMA = {"minimum": 0}
_TAX_YEAR_LIMIT = SQLITE_INTEGER_MAX + 1
_TAX_YEAR_SCHEMA = {"minimum": 0, "exclusiveMaximum": _TAX_YEAR_LIMIT}


def _parse_strict_query_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError("must be true or false")


def _parse_strict_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("must be a whole number")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if "_" in value:
            raise ValueError("must be a whole number") from None
        try:
            return int(value)
        except ValueError:
            raise ValueError("must be a whole number") from None
    raise ValueError("must be a whole number")


def _parse_strict_decimal(value: Any) -> Any:
    if isinstance(value, str) and "_" in value:
        raise ValueError("must be a decimal number") from None
    return value


StrictQueryBool = Annotated[
    bool,
    BeforeValidator(_parse_strict_query_bool),
    Query(),
]
StrictInt = Annotated[int, BeforeValidator(_parse_strict_int)]
StrictDecimal = Annotated[Decimal, BeforeValidator(_parse_strict_decimal)]
NonNegativeStrictIntQuery = Annotated[
    StrictInt,
    Query(ge=0, json_schema_extra=_NON_NEGATIVE_INTEGER_SCHEMA),
]
NonNegativeStrictDecimalQuery = Annotated[
    StrictDecimal,
    Query(ge=0, json_schema_extra={"minimum": 0}),
]
PositiveStrictDecimalQuery = Annotated[
    StrictDecimal,
    Query(gt=0, json_schema_extra={"exclusiveMinimum": 0}),
]
TaxYearPath = Annotated[
    StrictInt,
    ApiPath(ge=0, lt=_TAX_YEAR_LIMIT, json_schema_extra=_TAX_YEAR_SCHEMA),
]
TaxYearQuery = Annotated[
    StrictInt,
    Query(ge=0, lt=_TAX_YEAR_LIMIT, json_schema_extra=_TAX_YEAR_SCHEMA),
]


class CalculateRequest(BaseModel):
    year: int = Field(strict=True, ge=0, lt=_TAX_YEAR_LIMIT)
    filing_status: str = "single"
    gross_income: StrictDecimal = Field(ge=0)
    include_employer_payroll_tax: bool = Field(default=False, strict=True)
    dependent_count: int = Field(default=0, ge=0, strict=True)
    secondary_income: StrictDecimal = Field(default=Decimal("0"), ge=Decimal("0"))
    pretax_deduction_mode: PretaxDeductionMode = PRETAX_DEDUCTION_MODE_MAX_AVAILABLE

    @model_validator(mode="after")
    def validate_income_split(self) -> "CalculateRequest":
        gross_income = _try_round_query_money(self.gross_income)
        secondary_income = _try_round_query_money(self.secondary_income)
        if gross_income is None or secondary_income is None:
            if _has_supported_tax_parameters(self.year, self.filing_status):
                return self
            gross_income = self.gross_income
            secondary_income = self.secondary_income
        if secondary_income > gross_income:
            raise ValueError("secondary_income cannot exceed gross_income")
        return self


class PayrollBreakdownResponse(BaseModel):
    label: str
    gross_income: str
    payroll_wages: str
    employee_social_security_tax: str
    employee_medicare_tax: str
    employee_additional_medicare_tax: str
    total_employee_payroll_tax: str
    employer_social_security_tax: str
    employer_medicare_tax: str
    total_employer_payroll_tax: str
    total_payroll_tax: str


class TaxBreakdownResponse(BaseModel):
    code: str
    label: str
    amount: str


class TaxBurdenResponse(BaseModel):
    gross_income: str
    employee_401k_contribution: str
    health_fsa_contribution: str
    dependent_care_fsa_contribution: str
    total_pretax_deductions: str
    taxable_income: str
    federal_income_tax: str
    employee_social_security_tax: str
    employee_medicare_tax: str
    employee_additional_medicare_tax: str
    total_employee_payroll_tax: str
    total_employee_tax: str
    effective_employee_tax_rate: str
    marginal_employee_tax_rate: str
    employer_social_security_tax: str
    employer_medicare_tax: str
    total_employer_payroll_tax: str
    total_tax_with_employer_payroll: str
    marginal_tax_rate_with_employer_payroll: str
    payroll_breakdown: list[PayrollBreakdownResponse]
    tax_breakdown: list[TaxBreakdownResponse]


class IncomeSeriesResponse(BaseModel):
    rows: list[TaxBurdenResponse]
    marginal_breakpoint_incomes: list[str]


def create_app(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    *,
    initialize_database_on_create: bool = True,
) -> FastAPI:
    """Create the API app and optionally defer database initialization.

    The default preserves the factory's eager initialization behavior. The
    module-level ASGI app uses deferred initialization to avoid creating the
    SQLite database during import.
    """
    app = FastAPI(title="Tax Explorer API")
    app.state.database_path = Path(database_path)
    app.state.database_initialized = False
    if initialize_database_on_create:
        _initialize_app_database(app)

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
    def filing_statuses(year: TaxYearPath) -> dict[str, list[dict[str, str]]]:
        with _database(app) as connection:
            statuses = (
                get_filing_statuses(connection, year)
                if is_tax_year_available(connection, year)
                else []
            )
        if not statuses:
            raise HTTPException(
                status_code=404, detail=f"No filing statuses for {year}"
            )
        return {"statuses": statuses}

    @app.get("/api/tax-years/{year}/parameters")
    def tax_parameters(
        year: TaxYearPath, filing_status: str = Query(default="single")
    ) -> dict[str, Any]:
        try:
            with _database(app) as connection:
                federal = load_federal_tax_parameters(connection, year, filing_status)
                payroll = load_payroll_tax_parameters(connection, year)
                pretax = load_pretax_deduction_parameters(connection, year)
                available = is_tax_year_available(connection, year)
        except ValueError as exc:
            raise _parameter_http_exception(exc) from exc
        if not available:
            raise HTTPException(status_code=404, detail=f"No tax parameters for {year}")

        return {
            "federal": _federal_to_response(federal),
            "payroll": _dataclass_to_response(payroll),
            "pretax_deductions": _dataclass_to_response(pretax),
        }

    @app.post("/api/calculate")
    def calculate(request: CalculateRequest) -> TaxBurdenResponse:
        try:
            _prevalidate_supported_calculate_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

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
        return TaxBurdenResponse(
            **_tax_burden_to_response(
                result,
                include_employer_payroll_tax=request.include_employer_payroll_tax,
            )
        )

    @app.get("/api/income-series")
    def income_series(
        year: TaxYearQuery,
        filing_status: str = Query(default="single"),
        start: NonNegativeStrictDecimalQuery = Decimal("0"),
        stop: NonNegativeStrictDecimalQuery = Decimal("500000"),
        step: PositiveStrictDecimalQuery = Decimal("10000"),
        include_employer_payroll_tax: StrictQueryBool = False,
        include_marginal_breakpoints: StrictQueryBool = False,
        dependent_count: NonNegativeStrictIntQuery = 0,
        secondary_income: NonNegativeStrictDecimalQuery = Decimal("0"),
        pretax_deduction_mode: PretaxDeductionMode = Query(
            default=PRETAX_DEDUCTION_MODE_MAX_AVAILABLE
        ),
    ) -> IncomeSeriesResponse:
        try:
            _prevalidate_supported_income_series_request(
                year=year,
                filing_status=filing_status,
                start=start,
                stop=stop,
                step=step,
                secondary_income=secondary_income,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        try:
            federal, payroll, pretax = _load_parameters(app, year, filing_status)
        except ValueError as exc:
            raise _parameter_http_exception(exc) from exc

        try:
            series = calculate_income_series(
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

        return IncomeSeriesResponse(
            rows=[
                _tax_burden_to_response(
                    row,
                    include_employer_payroll_tax=include_employer_payroll_tax,
                )
                for row in series.rows
            ],
            marginal_breakpoint_incomes=[
                _decimal_to_string(income)
                for income in series.marginal_breakpoint_incomes
            ],
        )

    _preserve_exact_tax_year_openapi_limit(app)
    return app


def _preserve_exact_tax_year_openapi_limit(app: FastAPI) -> None:
    generated_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        schema = generated_openapi()
        year_schema = schema["components"]["schemas"]["CalculateRequest"][
            "properties"
        ]["year"]
        year_schema["exclusiveMaximum"] = _TAX_YEAR_LIMIT
        return schema

    app.openapi = openapi


@contextmanager
def _database(app: FastAPI) -> Iterator[Any]:
    if not app.state.database_initialized:
        _initialize_app_database(app)
    connection = connect(app.state.database_path)
    try:
        yield connection
    finally:
        connection.close()


def _initialize_app_database(app: FastAPI) -> None:
    bootstrap = initialize_database(app.state.database_path)
    bootstrap.close()
    app.state.database_initialized = True


def _load_parameters(
    app: FastAPI, year: int, filing_status: str
) -> tuple[FederalTaxParameters, PayrollTaxParameters, PretaxDeductionParameters]:
    with _database(app) as connection:
        federal = load_federal_tax_parameters(connection, year, filing_status)
        payroll = load_payroll_tax_parameters(connection, year)
        pretax = load_pretax_deduction_parameters(connection, year)
        available = is_tax_year_available(connection, year)
    if not available:
        raise ValueError(f"No tax parameters for {year}")
    return federal, payroll, pretax


def _prevalidate_supported_income_series_request(
    *,
    year: int,
    filing_status: str,
    start: Decimal,
    stop: Decimal,
    step: Decimal,
    secondary_income: Decimal,
) -> None:
    if not _has_supported_tax_parameters(year, filing_status):
        return

    start_amount = _rounded_query_money(start, "start")
    stop_amount = _rounded_query_money(stop, "stop")
    step_amount = _rounded_query_money(step, "step")
    if step_amount <= 0:
        raise ValueError("step must be positive")
    if start_amount > stop_amount:
        raise ValueError("start must be less than or equal to stop")
    secondary_income_amount = _rounded_query_money(
        secondary_income, "secondary_income"
    )
    if secondary_income_amount == 0:
        return
    if filing_status != "married_joint":
        raise ValueError("secondary_income is only supported for married_joint")
    if secondary_income_amount > stop_amount:
        raise ValueError("secondary_income cannot exceed stop")


def _prevalidate_supported_calculate_request(request: CalculateRequest) -> None:
    if not _has_supported_tax_parameters(request.year, request.filing_status):
        return

    _rounded_query_money(request.gross_income, "gross_income")
    secondary_income_amount = _rounded_query_money(
        request.secondary_income, "secondary_income"
    )
    if secondary_income_amount > 0 and request.filing_status != "married_joint":
        raise ValueError("secondary_income is only supported for married_joint")


def _has_supported_tax_parameters(year: int, filing_status: str) -> bool:
    return year == DEFAULT_TAX_YEAR and filing_status in FILING_STATUS_CHOICES


def _rounded_query_money(value: Decimal, field_name: str) -> Decimal:
    rounded_value = _try_round_query_money(value)
    if rounded_value is None:
        raise ValueError(f"{field_name} must fit cents precision") from None
    return rounded_value


def _try_round_query_money(value: Decimal) -> Decimal | None:
    try:
        return value.quantize(MONEY, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


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


def _tax_burden_to_response(
    result: TaxBurden, *, include_employer_payroll_tax: bool
) -> dict[str, Any]:
    response = {
        key: _value_to_response(value)
        for key, value in asdict(result).items()
    }
    response["tax_breakdown"] = _tax_breakdown_to_response(
        result,
        include_employer_payroll_tax=include_employer_payroll_tax,
    )
    return response


def _tax_breakdown_to_response(
    result: TaxBurden, *, include_employer_payroll_tax: bool
) -> list[dict[str, str]]:
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
    if include_employer_payroll_tax:
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


app = create_app(initialize_database_on_create=False)
