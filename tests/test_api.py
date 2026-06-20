import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tax_explorer.api import create_app
from tax_explorer.database import connect


INVALID_PERSISTED_PARAMETER_DETAIL = "social_security_rate must be a finite decimal"
INVALID_FEDERAL_BRACKET_START_DETAIL = "federal tax brackets must start at 0.00"
MISSING_ADDITIONAL_MEDICARE_THRESHOLD_DETAIL = (
    "additional_medicare_threshold missing for 2026 married_joint"
)


def create_test_client(tmp_path):
    return TestClient(create_app(database_path=tmp_path / "tax.sqlite3"))


def create_deferred_test_client(database_path):
    return TestClient(
        create_app(
            database_path=database_path,
            initialize_database_on_create=False,
        )
    )


def create_corrupted_payroll_test_client(tmp_path):
    database_path = tmp_path / "tax.sqlite3"
    client = TestClient(create_app(database_path=database_path))
    corrupt_payroll_rate(database_path)
    return client


def create_corrupted_federal_bracket_test_client(tmp_path):
    database_path = tmp_path / "tax.sqlite3"
    client = TestClient(create_app(database_path=database_path))
    corrupt_federal_bracket_start(database_path)
    return client


def create_missing_additional_medicare_threshold_test_client(tmp_path):
    database_path = tmp_path / "tax.sqlite3"
    client = TestClient(create_app(database_path=database_path))
    delete_additional_medicare_threshold(database_path)
    return client


def corrupt_payroll_rate(database_path):
    with connect(database_path) as connection:
        connection.execute(
            """
            UPDATE payroll_tax_parameters
            SET social_security_rate = ?
            WHERE year = ?
            """,
            ("NaN", 2026),
        )
        connection.commit()


def corrupt_federal_bracket_start(database_path):
    with connect(database_path) as connection:
        connection.execute(
            """
            UPDATE federal_tax_brackets
            SET lower_bound = ?
            WHERE year = ? AND filing_status = ? AND lower_bound = ?
            """,
            ("100.00", 2026, "single", "0.00"),
        )
        connection.commit()


def delete_additional_medicare_threshold(database_path):
    with connect(database_path) as connection:
        connection.execute(
            """
            DELETE FROM additional_medicare_thresholds
            WHERE year = ? AND filing_status = ?
            """,
            (2026, "married_joint"),
        )
        connection.commit()


def assert_invalid_persisted_parameter_response(response):
    assert response.status_code == 422
    assert response.json()["detail"] == INVALID_PERSISTED_PARAMETER_DETAIL


EXPECTED_ADDITIONAL_MEDICARE_THRESHOLDS = {
    "single": "200000.00",
    "married_joint": "250000.00",
    "married_separate": "125000.00",
    "head_of_household": "200000.00",
}


def api_subprocess_env() -> dict[str, str]:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("TAX_EXPLORER_DB", None)
    env["PYTHONPATH"] = str(repo_root / "src")
    return env


def test_importing_api_module_does_not_create_default_sqlite_file(tmp_path):
    code = (
        "from pathlib import Path\n"
        "import tax_explorer.api\n"
        "assert not Path('data/tax_explorer.sqlite3').exists()\n"
    )

    subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=api_subprocess_env(),
        check=True,
    )


def test_module_level_app_initializes_database_on_first_data_request(tmp_path):
    code = (
        "from pathlib import Path\n"
        "from fastapi.testclient import TestClient\n"
        "from tax_explorer.api import app\n"
        "database_path = Path('data/tax_explorer.sqlite3')\n"
        "assert not database_path.exists()\n"
        "response = TestClient(app).get('/api/tax-years')\n"
        "assert response.status_code == 200\n"
        "assert response.json() == {'years': [2026]}\n"
        "assert database_path.exists()\n"
    )

    subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=api_subprocess_env(),
        check=True,
    )


def numeric_schema(schema):
    return next(
        (candidate for candidate in schema.get("anyOf", []) if "minimum" in candidate),
        schema,
    )


def parameter_schema(parameters, name):
    return next(
        parameter["schema"] for parameter in parameters if parameter["name"] == name
    )


def assert_pretax_mode_validation_error(response, expected_loc):
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0] == {
        "type": "literal_error",
        "loc": expected_loc,
        "msg": "Input should be 'max_available' or 'gradual_phase_in'",
        "input": "unknown",
        "ctx": {"expected": "'max_available' or 'gradual_phase_in'"},
    }


def test_lists_available_tax_years(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/tax-years")

    assert response.status_code == 200
    assert response.json() == {"years": [2026]}


def test_tax_years_excludes_incomplete_parameter_sets(tmp_path):
    database_path = tmp_path / "tax.sqlite3"
    client = TestClient(create_app(database_path=database_path))
    with connect(database_path) as connection:
        connection.execute(
            "INSERT INTO tax_years (year, label) VALUES (?, ?)",
            (2030, "Tax Year 2030"),
        )
        connection.commit()

    response = client.get("/api/tax-years")

    assert response.status_code == 200
    assert response.json() == {"years": [2026]}


def test_lists_filing_statuses_for_tax_year(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/tax-years/2026/filing-statuses")

    assert response.status_code == 200
    assert response.json() == {
        "statuses": [
            {"code": "single", "label": "Single"},
            {"code": "married_joint", "label": "Married filing jointly"},
            {"code": "married_separate", "label": "Married filing separately"},
            {"code": "head_of_household", "label": "Head of household"},
        ]
    }


def test_filing_statuses_exclude_incomplete_tax_years(tmp_path):
    database_path = tmp_path / "tax.sqlite3"
    client = TestClient(create_app(database_path=database_path))
    with connect(database_path) as connection:
        connection.execute(
            "INSERT INTO tax_years (year, label) VALUES (?, ?)",
            (2030, "Tax Year 2030"),
        )
        connection.execute(
            """
            INSERT INTO federal_tax_parameters
                (year, filing_status, standard_deduction)
            VALUES (?, ?, ?)
            """,
            (2030, "single", "17000.00"),
        )
        connection.execute(
            """
            INSERT INTO federal_tax_brackets
                (year, filing_status, lower_bound, rate)
            VALUES (?, ?, ?, ?)
            """,
            (2030, "single", "0.00", "0.10"),
        )
        connection.commit()

    response = client.get("/api/tax-years/2030/filing-statuses")

    assert response.status_code == 404
    assert response.json()["detail"] == "No filing statuses for 2030"


@pytest.mark.parametrize(
    ("method", "path", "kwargs", "year_loc"),
    [
        ("get", "/api/tax-years/-1/filing-statuses", {}, ["path", "year"]),
        ("get", "/api/tax-years/-1/parameters", {}, ["path", "year"]),
        (
            "get",
            "/api/income-series",
            {
                "params": {
                    "year": -1,
                    "filing_status": "single",
                    "start": "0",
                    "stop": "100000",
                    "step": "10000",
                }
            },
            ["query", "year"],
        ),
        (
            "post",
            "/api/calculate",
            {
                "json": {
                    "year": -1,
                    "filing_status": "single",
                    "gross_income": "100000",
                }
            },
            ["body", "year"],
        ),
    ],
)
def test_api_rejects_negative_years_before_database_initialization(
    tmp_path,
    method,
    path,
    kwargs,
    year_loc,
):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    year_error = next(error for error in detail if error["loc"] == year_loc)
    assert year_error["type"] == "greater_than_equal"
    assert year_error["ctx"] == {"ge": 0}
    assert not database_path.exists()


def test_returns_parameters_for_tax_year(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/tax-years/2026/parameters")

    assert response.status_code == 200
    body = response.json()
    assert body["federal"]["tax_year"] == 2026
    assert body["federal"]["filing_status"] == "single"
    assert body["federal"]["standard_deduction"] == "16100.00"
    assert body["federal"]["brackets"][0] == {
        "lower_bound": "0.00",
        "rate": "0.10",
    }
    assert body["payroll"]["social_security_wage_base"] == "184500.00"
    assert body["payroll"]["additional_medicare_threshold_single"] == "200000.00"
    assert body["pretax_deductions"] == {
        "tax_year": 2026,
        "employee_401k_limit": "24500.00",
        "health_fsa_limit": "3400.00",
        "dependent_care_fsa_limit": "7500.00",
        "gradual_phase_in_start_rate": "0.01",
    }
    assert (
        body["payroll"]["additional_medicare_thresholds"]
        == EXPECTED_ADDITIONAL_MEDICARE_THRESHOLDS
    )


def test_returns_parameters_for_selected_filing_status(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/tax-years/2026/parameters",
        params={"filing_status": "head_of_household"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["federal"]["filing_status"] == "head_of_household"
    assert body["federal"]["standard_deduction"] == "24150.00"
    assert body["federal"]["brackets"][1] == {
        "lower_bound": "17700.00",
        "rate": "0.12",
    }


def test_parameters_report_invalid_persisted_values_as_unprocessable(tmp_path):
    client = create_corrupted_payroll_test_client(tmp_path)

    response = client.get("/api/tax-years/2026/parameters")

    assert_invalid_persisted_parameter_response(response)


def test_parameters_reject_federal_brackets_without_zero_lower_bound(tmp_path):
    client = create_corrupted_federal_bracket_test_client(tmp_path)

    response = client.get("/api/tax-years/2026/parameters")

    assert response.status_code == 422
    assert response.json()["detail"] == INVALID_FEDERAL_BRACKET_START_DETAIL


def test_parameters_reject_missing_additional_medicare_threshold(tmp_path):
    client = create_missing_additional_medicare_threshold_test_client(tmp_path)

    response = client.get("/api/tax-years/2026/parameters")

    assert response.status_code == 422
    assert response.json()["detail"] == MISSING_ADDITIONAL_MEDICARE_THRESHOLD_DETAIL


def test_calculates_tax_burden_from_database_parameters(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": 2026,
            "filing_status": "single",
            "gross_income": "100000",
            "include_employer_payroll_tax": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["gross_income"] == "100000.00"
    assert body["employee_401k_contribution"] == "24500.00"
    assert body["health_fsa_contribution"] == "3400.00"
    assert body["dependent_care_fsa_contribution"] == "0.00"
    assert body["total_pretax_deductions"] == "27900.00"
    assert body["taxable_income"] == "56000.00"
    assert body["total_employee_tax"] == "14421.90"
    assert body["effective_employee_tax_rate"] == "0.1442"


def test_calculate_uses_dependent_care_fsa_when_dependents_are_present(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": 2026,
            "filing_status": "single",
            "gross_income": "100000",
            "dependent_count": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["dependent_care_fsa_contribution"] == "7500.00"
    assert body["total_pretax_deductions"] == "35400.00"
    assert body["taxable_income"] == "48500.00"
    assert body["employee_social_security_tax"] == "5524.20"
    assert body["employee_medicare_tax"] == "1291.95"
    assert body["total_employee_tax"] == "12388.15"


def test_calculate_uses_secondary_income_for_married_joint_dual_earners(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": 2026,
            "filing_status": "married_joint",
            "gross_income": "300000",
            "secondary_income": "150000",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["employee_401k_contribution"] == "49000.00"
    assert body["health_fsa_contribution"] == "6800.00"
    assert body["total_pretax_deductions"] == "55800.00"
    assert body["taxable_income"] == "212000.00"
    assert body["employee_social_security_tax"] == "18178.40"
    assert body["employee_medicare_tax"] == "4251.40"
    assert body["employee_additional_medicare_tax"] == "388.80"
    assert body["total_employee_tax"] == "58894.60"


def test_calculate_reports_invalid_persisted_values_as_unprocessable(tmp_path):
    client = create_corrupted_payroll_test_client(tmp_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": 2026,
            "filing_status": "single",
            "gross_income": "100000",
        },
    )

    assert_invalid_persisted_parameter_response(response)


def test_calculate_response_includes_dual_earner_payroll_breakdown(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": 2026,
            "filing_status": "married_joint",
            "gross_income": "300000",
            "secondary_income": "150000",
            "include_employer_payroll_tax": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["payroll_breakdown"] == [
        {
            "label": "Income 1",
            "gross_income": "150000.00",
            "payroll_wages": "146600.00",
            "employee_social_security_tax": "9089.20",
            "employee_medicare_tax": "2125.70",
            "employee_additional_medicare_tax": "194.40",
            "total_employee_payroll_tax": "11409.30",
            "employer_social_security_tax": "9089.20",
            "employer_medicare_tax": "2125.70",
            "total_employer_payroll_tax": "11214.90",
            "total_payroll_tax": "22624.20",
        },
        {
            "label": "Income 2",
            "gross_income": "150000.00",
            "payroll_wages": "146600.00",
            "employee_social_security_tax": "9089.20",
            "employee_medicare_tax": "2125.70",
            "employee_additional_medicare_tax": "194.40",
            "total_employee_payroll_tax": "11409.30",
            "employer_social_security_tax": "9089.20",
            "employer_medicare_tax": "2125.70",
            "total_employer_payroll_tax": "11214.90",
            "total_payroll_tax": "22624.20",
        },
        {
            "label": "Total",
            "gross_income": "300000.00",
            "payroll_wages": "293200.00",
            "employee_social_security_tax": "18178.40",
            "employee_medicare_tax": "4251.40",
            "employee_additional_medicare_tax": "388.80",
            "total_employee_payroll_tax": "22818.60",
            "employer_social_security_tax": "18178.40",
            "employer_medicare_tax": "4251.40",
            "total_employer_payroll_tax": "22429.80",
            "total_payroll_tax": "45248.40",
        },
    ]


def test_calculate_rejects_secondary_income_for_non_joint_filers(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": 2026,
            "filing_status": "single",
            "gross_income": "100000",
            "secondary_income": "25000",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "secondary_income is only supported for married_joint"
    )


def test_calculate_prevalidates_secondary_income_for_non_joint_before_database_init(
    tmp_path,
):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": 2026,
            "filing_status": "single",
            "gross_income": "100000",
            "secondary_income": "25000",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "secondary_income is only supported for married_joint"
    )
    assert not database_path.exists()


def test_calculate_prevalidates_gross_income_precision_before_secondary_status(
    tmp_path,
):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": 2026,
            "filing_status": "single",
            "gross_income": "1e27",
            "secondary_income": "25000",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "gross_income must fit cents precision"
    assert not database_path.exists()


def test_calculate_prevalidates_secondary_income_precision_before_split_bounds(
    tmp_path,
):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": 2026,
            "filing_status": "married_joint",
            "gross_income": "100000",
            "secondary_income": "1e27",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "secondary_income must fit cents precision"
    assert not database_path.exists()


@pytest.mark.parametrize(
    ("year", "filing_status"),
    [(2030, "single"), (2026, "unsupported")],
)
def test_calculate_preserves_unsupported_split_bounds_for_unroundable_secondary(
    tmp_path,
    year,
    filing_status,
):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": year,
            "filing_status": filing_status,
            "gross_income": "100000",
            "secondary_income": "1e27",
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"] == ["body"]
    assert "secondary_income cannot exceed gross_income" in detail[0]["msg"]
    assert not database_path.exists()


@pytest.mark.parametrize(
    ("year", "filing_status", "expected_detail"),
    [
        (2030, "single", "No federal tax parameters for 2030 single"),
        (
            2026,
            "unsupported",
            "No federal tax parameters for 2026 unsupported",
        ),
    ],
)
def test_calculate_preserves_unknown_parameter_errors_for_secondary_income(
    tmp_path,
    year,
    filing_status,
    expected_detail,
):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": year,
            "filing_status": filing_status,
            "gross_income": "100000",
            "secondary_income": "25000",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == expected_detail
    assert database_path.exists()


def test_calculate_rejects_secondary_income_above_gross_income_as_request_validation(
    tmp_path,
):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": 2026,
            "filing_status": "married_joint",
            "gross_income": "100000",
            "secondary_income": "120000",
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"] == ["body"]
    assert "secondary_income cannot exceed gross_income" in detail[0]["msg"]


def test_calculate_rejects_negative_dependent_count(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": 2026,
            "filing_status": "single",
            "gross_income": "100000",
            "dependent_count": -1,
        },
    )

    assert response.status_code == 422


def test_calculate_rejects_coerced_year_request_values(tmp_path):
    client = create_test_client(tmp_path)

    for year in (True, False, "2026"):
        response = client.post(
            "/api/calculate",
            json={
                "year": year,
                "filing_status": "single",
                "gross_income": "100000",
            },
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, list)
        year_error = next(
            error for error in detail if error["loc"] == ["body", "year"]
        )
        assert year_error["type"] == "int_type"


def test_calculate_rejects_coerced_dependent_count_request_values(tmp_path):
    client = create_test_client(tmp_path)

    for dependent_count in (True, False, "1"):
        response = client.post(
            "/api/calculate",
            json={
                "year": 2026,
                "filing_status": "single",
                "gross_income": "100000",
                "dependent_count": dependent_count,
            },
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, list)
        dependent_count_error = next(
            error
            for error in detail
            if error["loc"] == ["body", "dependent_count"]
        )
        assert dependent_count_error["type"] == "int_type"


def test_calculate_rejects_coerced_employer_payroll_request_values(tmp_path):
    client = create_test_client(tmp_path)

    for include_employer_payroll_tax in ("true", "false", 1, 0):
        response = client.post(
            "/api/calculate",
            json={
                "year": 2026,
                "filing_status": "single",
                "gross_income": "100000",
                "include_employer_payroll_tax": include_employer_payroll_tax,
            },
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, list)
        employer_payroll_error = next(
            error
            for error in detail
            if error["loc"] == ["body", "include_employer_payroll_tax"]
        )
        assert employer_payroll_error["type"] == "bool_type"


def test_calculate_rejects_unknown_pretax_deduction_mode_as_request_validation(
    tmp_path,
):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": 2026,
            "filing_status": "single",
            "gross_income": "100000",
            "pretax_deduction_mode": "unknown",
        },
    )

    assert_pretax_mode_validation_error(response, ["body", "pretax_deduction_mode"])


def test_openapi_documents_request_validation_constraints(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    calculate_mode_schema = openapi["components"]["schemas"]["CalculateRequest"][
        "properties"
    ]["pretax_deduction_mode"]
    calculate_year_schema = openapi["components"]["schemas"]["CalculateRequest"][
        "properties"
    ]["year"]
    calculate_dependent_count_schema = openapi["components"]["schemas"][
        "CalculateRequest"
    ]["properties"]["dependent_count"]
    calculate_secondary_income_schema = openapi["components"]["schemas"][
        "CalculateRequest"
    ]["properties"]["secondary_income"]
    assert calculate_mode_schema["enum"] == [
        "max_available",
        "gradual_phase_in",
    ]
    assert calculate_year_schema["minimum"] == 0
    assert calculate_dependent_count_schema["minimum"] == 0
    assert numeric_schema(calculate_secondary_income_schema)["minimum"] == 0

    income_series_parameters = openapi["paths"]["/api/income-series"]["get"][
        "parameters"
    ]
    assert parameter_schema(income_series_parameters, "year")["minimum"] == 0
    assert parameter_schema(income_series_parameters, "pretax_deduction_mode")[
        "enum"
    ] == [
        "max_available",
        "gradual_phase_in",
    ]
    assert parameter_schema(income_series_parameters, "dependent_count")[
        "minimum"
    ] == 0
    assert (
        numeric_schema(parameter_schema(income_series_parameters, "secondary_income"))[
            "minimum"
        ]
        == 0
    )
    for field_name in (
        "include_employer_payroll_tax",
        "include_marginal_breakpoints",
    ):
        boolean_schema = parameter_schema(income_series_parameters, field_name)
        assert boolean_schema["type"] == "boolean"
        assert boolean_schema["default"] is False
    for path in (
        "/api/tax-years/{year}/filing-statuses",
        "/api/tax-years/{year}/parameters",
    ):
        path_parameters = openapi["paths"][path]["get"]["parameters"]
        assert parameter_schema(path_parameters, "year")["minimum"] == 0


def test_calculate_response_breaks_tax_down_by_component(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/calculate",
        json={
            "year": 2026,
            "filing_status": "single",
            "gross_income": "100000",
            "include_employer_payroll_tax": False,
            "pretax_deduction_mode": "gradual_phase_in",
        },
    )

    assert response.status_code == 200
    assert response.json()["tax_breakdown"] == [
        {
            "code": "federal_income_tax",
            "label": "Federal income tax",
            "amount": "12411.25",
        },
        {
            "code": "employee_social_security_tax",
            "label": "Social Security tax",
            "amount": "6173.94",
        },
        {
            "code": "employee_medicare_tax",
            "label": "Medicare tax",
            "amount": "1443.91",
        },
        {
            "code": "employee_additional_medicare_tax",
            "label": "Additional Medicare tax",
            "amount": "0.00",
        },
    ]


def test_returns_income_series_from_database_parameters(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "0",
            "stop": "100000",
            "step": "50000",
        },
    )

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert [row["gross_income"] for row in rows] == [
        "0.00",
        "50000.00",
        "100000.00",
    ]
    assert rows[-1]["total_employee_tax"] == "14421.90"


def test_income_series_reports_invalid_persisted_values_as_unprocessable(tmp_path):
    client = create_corrupted_payroll_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "0",
            "stop": "100000",
            "step": "50000",
        },
    )

    assert_invalid_persisted_parameter_response(response)


def test_income_series_can_include_marginal_breakpoints_and_rates(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "0",
            "stop": "250000",
            "step": "100000",
            "include_marginal_breakpoints": True,
        },
    )

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert [row["gross_income"] for row in rows] == [
        "0.00",
        "27900.00",
        "44000.00",
        "56400.00",
        "94400.00",
        "100000.00",
        "149700.00",
        "187900.00",
        "200000.00",
        "203400.00",
        "245775.00",
        "250000.00",
    ]
    assert rows[0]["marginal_employee_tax_rate"] == "0.0672"
    assert rows[1]["marginal_employee_tax_rate"] == "0.0765"
    assert rows[7]["marginal_employee_tax_rate"] == "0.2545"


def test_income_series_accepts_lowercase_boolean_query_strings(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "100000",
            "stop": "100000",
            "step": "50000",
            "include_employer_payroll_tax": "false",
            "include_marginal_breakpoints": "true",
        },
    )

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["gross_income"] == "100000.00"
    assert row["total_tax_with_employer_payroll"] == "14421.90"


def test_income_series_includes_lopsided_dual_earner_deduction_breakpoint(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "married_joint",
            "start": "0",
            "stop": "120000",
            "step": "120000",
            "include_marginal_breakpoints": True,
            "secondary_income": "5000",
        },
    )

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert [row["gross_income"] for row in rows] == [
        "0.00",
        "32900.00",
        "65100.00",
        "89900.00",
        "120000.00",
    ]
    assert rows[1]["total_pretax_deductions"] == "32900.00"


def test_income_series_accepts_gradual_pretax_deduction_mode(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "100000",
            "stop": "100000",
            "step": "50000",
            "pretax_deduction_mode": "gradual_phase_in",
        },
    )

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["total_pretax_deductions"] == "3448.87"
    assert row["employee_401k_contribution"] == "3028.58"
    assert row["health_fsa_contribution"] == "420.29"
    assert row["total_employee_tax"] == "20029.10"


def test_income_series_uses_dependent_care_fsa_when_dependents_are_present(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "100000",
            "stop": "100000",
            "step": "50000",
            "dependent_count": 2,
        },
    )

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["dependent_care_fsa_contribution"] == "7500.00"
    assert row["total_pretax_deductions"] == "35400.00"
    assert row["total_employee_tax"] == "12388.15"


def test_income_series_accepts_secondary_income_for_married_joint(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "married_joint",
            "start": "300000",
            "stop": "300000",
            "step": "50000",
            "secondary_income": "150000",
        },
    )

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["employee_401k_contribution"] == "49000.00"
    assert row["health_fsa_contribution"] == "6800.00"
    assert row["employee_social_security_tax"] == "18178.40"
    assert row["total_employee_tax"] == "58894.60"


def test_income_series_rejects_secondary_income_for_non_joint_filers(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "100000",
            "stop": "100000",
            "step": "50000",
            "secondary_income": "25000",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "secondary_income is only supported for married_joint"
    )


def test_income_series_prevalidates_secondary_income_for_non_joint_before_database_init(
    tmp_path,
):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "100000",
            "stop": "100000",
            "step": "50000",
            "secondary_income": "25000",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "secondary_income is only supported for married_joint"
    )
    assert not database_path.exists()


def test_income_series_rejects_secondary_income_above_stop(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "married_joint",
            "start": "0",
            "stop": "100000",
            "step": "50000",
            "secondary_income": "120000",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "secondary_income cannot exceed stop"


def test_income_series_prevalidates_secondary_income_above_stop_before_database_init(
    tmp_path,
):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "married_joint",
            "start": "0",
            "stop": "100000",
            "step": "50000",
            "secondary_income": "120000",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "secondary_income cannot exceed stop"
    assert not database_path.exists()


def test_income_series_rejects_negative_dependent_count(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "100000",
            "stop": "100000",
            "step": "50000",
            "dependent_count": -1,
        },
    )

    assert response.status_code == 422


def test_income_series_rejects_ambiguous_boolean_query_values(tmp_path):
    client = create_test_client(tmp_path)

    for field_name in (
        "include_employer_payroll_tax",
        "include_marginal_breakpoints",
    ):
        for query_value in ("1", "yes"):
            response = client.get(
                "/api/income-series",
                params={
                    "year": 2026,
                    "filing_status": "single",
                    "start": "100000",
                    "stop": "100000",
                    "step": "50000",
                    field_name: query_value,
                },
            )

            assert response.status_code == 422
            detail = response.json()["detail"]
            assert isinstance(detail, list)
            assert detail[0]["loc"] == ["query", field_name]


def test_income_series_rejects_unknown_pretax_deduction_mode(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "100000",
            "stop": "100000",
            "step": "50000",
            "pretax_deduction_mode": "unknown",
        },
    )

    assert_pretax_mode_validation_error(response, ["query", "pretax_deduction_mode"])


def test_income_series_rejects_reversed_income_range(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "100000",
            "stop": "0",
            "step": "10000",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "start must be less than or equal to stop"


def test_income_series_prevalidates_reversed_range_before_database_init(tmp_path):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "100000",
            "stop": "0",
            "step": "10000",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "start must be less than or equal to stop"
    assert not database_path.exists()


def test_income_series_compares_prevalidated_range_after_money_rounding(tmp_path):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "0.004",
            "stop": "0.003",
            "step": "1",
        },
    )

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert [row["gross_income"] for row in rows] == ["0.00"]
    assert database_path.exists()


def test_income_series_prevalidates_unroundable_range_before_database_init(tmp_path):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "1e27",
            "stop": "1e27",
            "step": "10000",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "start must fit cents precision"
    assert not database_path.exists()


def test_income_series_prevalidates_reversed_range_before_secondary_precision(
    tmp_path,
):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "married_joint",
            "start": "100000",
            "stop": "0",
            "step": "10000",
            "secondary_income": "1e27",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "start must be less than or equal to stop"
    assert not database_path.exists()


@pytest.mark.parametrize(
    ("step", "message"),
    [
        ("1e27", "step must fit cents precision"),
        ("0.004", "step must be positive"),
    ],
)
def test_income_series_prevalidates_invalid_step_before_database_init(
    tmp_path,
    step,
    message,
):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "0",
            "stop": "100000",
            "step": step,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == message
    assert not database_path.exists()


def test_income_series_prevalidates_step_before_secondary_precision(tmp_path):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "married_joint",
            "start": "0",
            "stop": "100000",
            "step": "0.004",
            "secondary_income": "1e27",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "step must be positive"
    assert not database_path.exists()


def test_income_series_preserves_unknown_year_error_for_invalid_range(tmp_path):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2030,
            "filing_status": "single",
            "start": "100000",
            "stop": "0",
            "step": "10000",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "No federal tax parameters for 2030 single"
    assert database_path.exists()


def test_income_series_preserves_unknown_status_error_for_invalid_range(tmp_path):
    database_path = tmp_path / "tax.sqlite3"
    client = create_deferred_test_client(database_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "unsupported",
            "start": "100000",
            "stop": "0",
            "step": "10000",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "No federal tax parameters for 2026 unsupported"
    )
    assert database_path.exists()


def test_income_series_rejects_excessive_row_count(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "0",
            "stop": "2001000",
            "step": "1000",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "income-series supports at most 2001 rows"


def test_income_series_breakdown_includes_employer_components_when_selected(
    tmp_path,
):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "single",
            "start": "100000",
            "stop": "100000",
            "step": "50000",
            "include_employer_payroll_tax": True,
        },
    )

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["total_tax_with_employer_payroll"] == "21811.80"
    assert row["tax_breakdown"] == [
        {
            "code": "federal_income_tax",
            "label": "Federal income tax",
            "amount": "7032.00",
        },
        {
            "code": "employee_social_security_tax",
            "label": "Social Security tax",
            "amount": "5989.20",
        },
        {
            "code": "employee_medicare_tax",
            "label": "Medicare tax",
            "amount": "1400.70",
        },
        {
            "code": "employee_additional_medicare_tax",
            "label": "Additional Medicare tax",
            "amount": "0.00",
        },
        {
            "code": "employer_social_security_tax",
            "label": "Employer Social Security tax",
            "amount": "5989.20",
        },
        {
            "code": "employer_medicare_tax",
            "label": "Employer Medicare tax",
            "amount": "1400.70",
        },
    ]


def test_income_series_uses_selected_filing_status_standard_deduction_and_brackets(
    tmp_path,
):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/income-series",
        params={
            "year": 2026,
            "filing_status": "married_joint",
            "start": "100000",
            "stop": "100000",
            "step": "50000",
        },
    )

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["taxable_income"] == "39900.00"
    assert row["federal_income_tax"] == "4292.00"
    assert row["total_employee_tax"] == "11681.90"
    assert row["effective_employee_tax_rate"] == "0.1168"


def test_rejects_unknown_tax_year(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/tax-years/2030/parameters")

    assert response.status_code == 404
    assert response.json()["detail"] == "No federal tax parameters for 2030 single"


def test_api_requests_do_not_reseed_existing_parameters(tmp_path):
    database_path = tmp_path / "tax.sqlite3"
    client = TestClient(create_app(database_path=database_path))
    with connect(database_path) as connection:
        connection.execute(
            """
            UPDATE federal_tax_parameters
            SET standard_deduction = ?
            WHERE year = ? AND filing_status = ?
            """,
            ("17000.00", 2026, "single"),
        )
        connection.commit()

    response = client.get("/api/tax-years/2026/parameters")

    assert response.status_code == 200
    assert response.json()["federal"]["standard_deduction"] == "17000.00"
