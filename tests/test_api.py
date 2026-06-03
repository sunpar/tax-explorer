from fastapi.testclient import TestClient

from tax_explorer.api import create_app
from tax_explorer.database import connect


def create_test_client(tmp_path):
    return TestClient(create_app(database_path=tmp_path / "tax.sqlite3"))


EXPECTED_ADDITIONAL_MEDICARE_THRESHOLDS = {
    "single": "200000.00",
    "married_joint": "250000.00",
    "married_separate": "125000.00",
    "head_of_household": "200000.00",
}


def test_lists_available_tax_years(tmp_path):
    client = create_test_client(tmp_path)

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
        "dependent_care_fsa_limit": "0.00",
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

    assert response.status_code == 422
    assert response.json()["detail"] == "unknown pretax_deduction_mode: unknown"


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
