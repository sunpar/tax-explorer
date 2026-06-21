import { afterEach, describe, expect, test, vi } from "vitest";
import {
  fetchFilingStatuses,
  fetchIncomeSeries,
  fetchTaxBurden,
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

  test("rejects malformed tax year discovery responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ years: [2026, "2025"] }), {
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
});
