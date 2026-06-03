from fastapi.testclient import TestClient

from tax_explorer.api import create_app


def test_lists_available_tax_years(tmp_path):
    client = TestClient(create_app(database_path=tmp_path / "tax.sqlite3"))

    response = client.get("/api/tax-years")

    assert response.status_code == 200
    assert response.json() == {"years": [2026]}


def test_returns_parameters_for_tax_year(tmp_path):
    client = TestClient(create_app(database_path=tmp_path / "tax.sqlite3"))

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


def test_calculates_tax_burden_from_database_parameters(tmp_path):
    client = TestClient(create_app(database_path=tmp_path / "tax.sqlite3"))

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
    assert body["taxable_income"] == "83900.00"
    assert body["total_employee_tax"] == "20820.00"
    assert body["effective_employee_tax_rate"] == "0.2082"


def test_returns_income_series_from_database_parameters(tmp_path):
    client = TestClient(create_app(database_path=tmp_path / "tax.sqlite3"))

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
    assert rows[-1]["total_employee_tax"] == "20820.00"


def test_rejects_unknown_tax_year(tmp_path):
    client = TestClient(create_app(database_path=tmp_path / "tax.sqlite3"))

    response = client.get("/api/tax-years/2030/parameters")

    assert response.status_code == 404
    assert response.json()["detail"] == "No federal tax parameters for 2030 single"
