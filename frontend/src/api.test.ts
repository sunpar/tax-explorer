import { afterEach, describe, expect, test, vi } from "vitest";
import {
  fetchFilingStatuses,
  fetchIncomeSeries,
  fetchTaxBurden,
  fetchTaxParameters,
  fetchTaxYears
} from "./api";

describe("api requests", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("uses FastAPI detail text for failed JSON responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "gross_income must be non-negative" }), {
        headers: { "Content-Type": "application/json" },
        status: 422
      })
    );

    await expect(
      fetchTaxBurden({
        year: 2026,
        filingStatus: "single",
        grossIncome: "-1",
        includeEmployerPayrollTax: false,
        dependentCount: 0,
        secondaryIncome: "0",
        pretaxDeductionMode: "max_available"
      })
    ).rejects.toMatchObject({
      message: "gross_income must be non-negative"
    });
  });

  test("formats FastAPI validation detail arrays from failed JSON responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: [
            {
              loc: ["query", "step"],
              msg: "Input should be greater than 0",
              type: "greater_than"
            }
          ]
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 422
        }
      )
    );

    await expect(
      fetchIncomeSeries({
        year: 2026,
        filingStatus: "single",
        start: "0",
        stop: "100000",
        step: "0",
        includeEmployerPayrollTax: false,
        dependentCount: 0,
        secondaryIncome: "0",
        pretaxDeductionMode: "max_available"
      })
    ).rejects.toMatchObject({
      message: "step: Input should be greater than 0"
    });
  });

  test("keeps plain text from failed responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("database unavailable", { status: 503 })
    );

    await expect(fetchTaxYears()).rejects.toMatchObject({
      message: "database unavailable"
    });
  });

  test("uses status fallback for empty failed responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("", { status: 500 })
    );

    await expect(fetchTaxYears()).rejects.toMatchObject({
      message: "Request failed with 500"
    });
  });

  test.each([
    { years: [2026, "2025"] },
    { years: [2026.5] },
    { years: [-1] }
  ])("rejects malformed tax year discovery responses", async (body) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status: 200
      })
    );

    await expect(fetchTaxYears()).rejects.toMatchObject({
      message: "Malformed tax year response"
    });
  });

  test("rejects malformed filing status discovery responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          statuses: [{ label: "Single" }]
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200
        }
      )
    );

    await expect(fetchFilingStatuses(2026)).rejects.toMatchObject({
      message: "Malformed filing status response"
    });
  });

  test.each([
    {},
    {
      federal: {
        tax_year: 2026,
        filing_status: "single",
        standard_deduction: "16100.00",
        brackets: [{ lower_bound: "0.00", rate: 0.1 }]
      },
      payroll: {
        tax_year: 2026,
        social_security_rate: "0.062",
        social_security_wage_base: "184500.00",
        medicare_rate: "0.0145",
        additional_medicare_rate: "0.009",
        additional_medicare_threshold_single: "200000.00",
        additional_medicare_thresholds: { single: "200000.00" }
      },
      pretax_deductions: {
        tax_year: 2026,
        employee_401k_limit: "24500.00",
        health_fsa_limit: "3400.00",
        dependent_care_fsa_limit: "7500.00",
        gradual_phase_in_start_rate: "0.01"
      }
    },
    {
      federal: {
        tax_year: 2026,
        filing_status: "single",
        standard_deduction: "16100.00",
        brackets: [{ lower_bound: "0.00", rate: "0.10" }]
      },
      payroll: {
        tax_year: 2026,
        social_security_rate: "0.062",
        social_security_wage_base: "184500.00",
        medicare_rate: "0.0145",
        additional_medicare_rate: "0.009",
        additional_medicare_threshold_single: "200000.00",
        additional_medicare_thresholds: { single: 200000 }
      },
      pretax_deductions: {
        tax_year: 2026,
        employee_401k_limit: "24500.00",
        health_fsa_limit: "3400.00",
        dependent_care_fsa_limit: "7500.00",
        gradual_phase_in_start_rate: "0.01"
      }
    }
  ])("rejects malformed tax parameter responses", async (body) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status: 200
      })
    );

    await expect(fetchTaxParameters(2026, "single")).rejects.toMatchObject({
      message: "Malformed tax parameter response"
    });
  });
});
