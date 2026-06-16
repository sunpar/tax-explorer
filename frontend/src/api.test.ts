import { afterEach, describe, expect, test, vi } from "vitest";
import { fetchTaxBurden, fetchTaxYears } from "./api";

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
});
