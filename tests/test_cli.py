import csv
import io

from tax_explorer import TaxScenario, calculate_tax_burden
from tax_explorer.cli import CSV_FIELDS, write_csv


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
