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

  const taxParameterResponse = {
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
      additional_medicare_thresholds: { single: "200000.00" }
    },
    pretax_deductions: {
      tax_year: 2026,
      employee_401k_limit: "24500.00",
      health_fsa_limit: "3400.00",
      dependent_care_fsa_limit: "7500.00",
      gradual_phase_in_start_rate: "0.01"
    }
  };

  const taxBurdenResponse = {
    gross_income: "100000.00",
    taxable_income: "56000.00",
    federal_income_tax: "7032.00",
    employee_social_security_tax: "5989.20",
    employee_medicare_tax: "1400.70",
    employee_additional_medicare_tax: "0.00",
    total_employee_payroll_tax: "7389.90",
    total_employee_tax: "14421.90",
    effective_employee_tax_rate: "0.1442",
    marginal_employee_tax_rate: "0.2965",
    employee_401k_contribution: "24500.00",
    health_fsa_contribution: "3400.00",
    dependent_care_fsa_contribution: "0.00",
    total_pretax_deductions: "27900.00",
    employer_social_security_tax: "0.00",
    employer_medicare_tax: "0.00",
    total_employer_payroll_tax: "0.00",
    total_tax_with_employer_payroll: "14421.90",
    marginal_tax_rate_with_employer_payroll: "0.2965",
    payroll_breakdown: [
      {
        label: "Income 1",
        gross_income: "100000.00",
        payroll_wages: "96600.00",
        employee_social_security_tax: "5989.20",
        employee_medicare_tax: "1400.70",
        employee_additional_medicare_tax: "0.00",
        total_employee_payroll_tax: "7389.90",
        employer_social_security_tax: "0.00",
        employer_medicare_tax: "0.00",
        total_employer_payroll_tax: "0.00",
        total_payroll_tax: "7389.90"
      }
    ],
    tax_breakdown: [
      {
        code: "federal_income_tax",
        label: "Federal income tax",
        amount: "7032.00"
      }
    ]
  };

  const seriesRequest = {
    year: 2026,
    filingStatus: "single",
    start: "0",
    stop: "100000",
    step: "10000",
    includeEmployerPayrollTax: false,
    dependentCount: 0,
    secondaryIncome: "0",
    pretaxDeductionMode: "max_available" as const
  };

  const calculateRequest = {
    year: 2026,
    filingStatus: "single",
    grossIncome: "100000",
    includeEmployerPayrollTax: false,
    dependentCount: 0,
    secondaryIncome: "0",
    pretaxDeductionMode: "max_available" as const
  };

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
    { years: [-1] },
    { years: [2026, 2026] },
    { years: [2026, 2025] }
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

  test.each([{ years: [] }, { years: [2025, 2026] }])(
    "returns valid tax year discovery responses",
    async (body) => {
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(JSON.stringify(body), {
          headers: { "Content-Type": "application/json" },
          status: 200
        })
      );

      await expect(fetchTaxYears()).resolves.toEqual(body.years);
    }
  );

  test("returns valid filing status discovery responses", async () => {
    const body = {
      statuses: [
        { code: "single", label: "Single" },
        { code: "married_joint", label: "Married filing jointly" }
      ]
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status: 200
      })
    );

    await expect(fetchFilingStatuses(2026)).resolves.toEqual(body.statuses);
  });

  test.each([
    { statuses: [] },
    { statuses: [{ label: "Single" }] },
    { statuses: [{ code: "", label: "Single" }] },
    { statuses: [{ code: "   ", label: "Single" }] },
    { statuses: [{ code: "single", label: "" }] },
    { statuses: [{ code: "single", label: "   " }] },
    {
      statuses: [
        { code: "single", label: "Single" },
        { code: "single", label: "Single duplicate" }
      ]
    }
  ])("rejects malformed filing status discovery responses", async (body) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status: 200
      })
    );

    await expect(fetchFilingStatuses(2026)).rejects.toMatchObject({
      message: "Malformed filing status response"
    });
  });

  test("returns valid tax parameter responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(taxParameterResponse), {
        headers: { "Content-Type": "application/json" },
        status: 200
      })
    );

    await expect(fetchTaxParameters(2026, "single")).resolves.toEqual(
      taxParameterResponse
    );
  });

  test("returns valid non-single tax parameter responses", async () => {
    const body = {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        filing_status: "married_joint"
      },
      payroll: {
        ...taxParameterResponse.payroll,
        additional_medicare_thresholds: { married_joint: "250000.00" }
      }
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status: 200
      })
    );

    await expect(fetchTaxParameters(2026, "married_joint")).resolves.toEqual(body);
  });

  test("returns signed zero federal bracket rates accepted by persisted validation", async () => {
    const body = {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        brackets: [{ lower_bound: "0.00", rate: "-0.00" }]
      }
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status: 200
      })
    );

    await expect(fetchTaxParameters(2026, "single")).resolves.toEqual(body);
  });

  test.each([
    {},
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        tax_year: 2025
      }
    },
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        filing_status: "married_joint"
      },
      payroll: {
        ...taxParameterResponse.payroll,
        additional_medicare_thresholds: { married_joint: "250000.00" }
      }
    },
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        standard_deduction: "oops"
      }
    },
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        standard_deduction: "-1.00"
      }
    },
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        brackets: [{ lower_bound: "0.00", rate: 0.1 }]
      }
    },
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        brackets: [{ lower_bound: "0.00", rate: "abc" }]
      }
    },
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        brackets: [{ lower_bound: "0.00", rate: "-0.10" }]
      }
    },
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        brackets: [{ lower_bound: "0.00", rate: "1.10" }]
      }
    },
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        brackets: [{ lower_bound: "0.00", rate: "1.0000000000000000001" }]
      }
    },
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        brackets: []
      }
    },
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        brackets: [{ lower_bound: "1000.00", rate: "0.10" }]
      }
    },
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        brackets: [
          { lower_bound: "0.00", rate: "0.10" },
          { lower_bound: "0.00", rate: "0.12" }
        ]
      }
    },
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        brackets: [
          { lower_bound: "0.00", rate: "0.10" },
          { lower_bound: "100000.00", rate: "0.24" },
          { lower_bound: "50000.00", rate: "0.22" }
        ]
      }
    },
    {
      ...taxParameterResponse,
      payroll: {
        ...taxParameterResponse.payroll,
        social_security_rate: "Infinity"
      }
    },
    {
      ...taxParameterResponse,
      payroll: {
        ...taxParameterResponse.payroll,
        social_security_wage_base: "-1.00"
      }
    },
    {
      ...taxParameterResponse,
      payroll: {
        ...taxParameterResponse.payroll,
        social_security_rate: "-0.10"
      }
    },
    {
      ...taxParameterResponse,
      payroll: {
        ...taxParameterResponse.payroll,
        medicare_rate: "1.10"
      }
    },
    {
      ...taxParameterResponse,
      payroll: {
        ...taxParameterResponse.payroll,
        additional_medicare_rate: "1.0000000000000000001"
      }
    },
    {
      ...taxParameterResponse,
      payroll: {
        ...taxParameterResponse.payroll,
        additional_medicare_threshold_single: "-1.00"
      }
    },
    {
      ...taxParameterResponse,
      payroll: {
        ...taxParameterResponse.payroll,
        additional_medicare_thresholds: { single: 200000 }
      }
    },
    {
      ...taxParameterResponse,
      payroll: {
        ...taxParameterResponse.payroll,
        additional_medicare_thresholds: ["200000.00"]
      }
    },
    {
      ...taxParameterResponse,
      federal: {
        ...taxParameterResponse.federal,
        filing_status: "married_joint"
      },
      payroll: {
        ...taxParameterResponse.payroll,
        additional_medicare_thresholds: { single: "200000.00" }
      }
    },
    {
      ...taxParameterResponse,
      payroll: {
        ...taxParameterResponse.payroll,
        additional_medicare_thresholds: { single: "oops" }
      }
    },
    {
      ...taxParameterResponse,
      payroll: {
        ...taxParameterResponse.payroll,
        additional_medicare_thresholds: { single: "-1.00" }
      }
    },
    {
      ...taxParameterResponse,
      pretax_deductions: {
        ...taxParameterResponse.pretax_deductions,
        health_fsa_limit: 3400
      }
    },
    {
      ...taxParameterResponse,
      pretax_deductions: {
        ...taxParameterResponse.pretax_deductions,
        employee_401k_limit: "-1.00"
      }
    },
    {
      ...taxParameterResponse,
      pretax_deductions: {
        ...taxParameterResponse.pretax_deductions,
        health_fsa_limit: "-0.01"
      }
    },
    {
      ...taxParameterResponse,
      pretax_deductions: {
        ...taxParameterResponse.pretax_deductions,
        dependent_care_fsa_limit: "-7500.00"
      }
    },
    {
      ...taxParameterResponse,
      pretax_deductions: {
        ...taxParameterResponse.pretax_deductions,
        gradual_phase_in_start_rate: "NaN"
      }
    },
    {
      ...taxParameterResponse,
      pretax_deductions: {
        ...taxParameterResponse.pretax_deductions,
        gradual_phase_in_start_rate: "-0.10"
      }
    },
    {
      ...taxParameterResponse,
      pretax_deductions: {
        ...taxParameterResponse.pretax_deductions,
        gradual_phase_in_start_rate: "1.10"
      }
    },
    {
      ...taxParameterResponse,
      pretax_deductions: {
        ...taxParameterResponse.pretax_deductions,
        gradual_phase_in_start_rate: "1.0000000000000000001"
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

  test("returns valid tax burden responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(taxBurdenResponse), {
        headers: { "Content-Type": "application/json" },
        status: 200
      })
    );

    await expect(fetchTaxBurden(calculateRequest)).resolves.toEqual(
      taxBurdenResponse
    );
  });

  test("returns signed zero tax burden amount responses", async () => {
    const body = {
      ...taxBurdenResponse,
      total_employee_tax: "-0.00",
      payroll_breakdown: [
        {
          ...taxBurdenResponse.payroll_breakdown[0],
          total_payroll_tax: "-0.00"
        }
      ],
      tax_breakdown: [
        {
          ...taxBurdenResponse.tax_breakdown[0],
          amount: "-0.00"
        }
      ]
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status: 200
      })
    );

    await expect(fetchTaxBurden(calculateRequest)).resolves.toEqual(body);
  });

  test.each([
    {},
    {
      ...taxBurdenResponse,
      gross_income: 100000
    },
    {
      ...taxBurdenResponse,
      effective_employee_tax_rate: "oops"
    },
    {
      ...taxBurdenResponse,
      total_employee_tax: "-1.00"
    },
    {
      ...taxBurdenResponse,
      payroll_breakdown: []
    },
    {
      ...taxBurdenResponse,
      payroll_breakdown: [
        {
          ...taxBurdenResponse.payroll_breakdown[0],
          total_payroll_tax: 7389.9
        }
      ]
    },
    {
      ...taxBurdenResponse,
      payroll_breakdown: [
        {
          ...taxBurdenResponse.payroll_breakdown[0],
          total_payroll_tax: "-1.00"
        }
      ]
    },
    {
      ...taxBurdenResponse,
      payroll_breakdown: [
        {
          ...taxBurdenResponse.payroll_breakdown[0],
          label: "   "
        }
      ]
    },
    {
      ...taxBurdenResponse,
      payroll_breakdown: [
        taxBurdenResponse.payroll_breakdown[0],
        {
          ...taxBurdenResponse.payroll_breakdown[0],
          gross_income: "0.00"
        }
      ]
    },
    {
      ...taxBurdenResponse,
      tax_breakdown: []
    },
    {
      ...taxBurdenResponse,
      tax_breakdown: [
        {
          ...taxBurdenResponse.tax_breakdown[0],
          code: ""
        }
      ]
    },
    {
      ...taxBurdenResponse,
      tax_breakdown: [
        {
          ...taxBurdenResponse.tax_breakdown[0],
          amount: "-1.00"
        }
      ]
    },
    {
      ...taxBurdenResponse,
      tax_breakdown: [
        {
          ...taxBurdenResponse.tax_breakdown[0],
          code: "   "
        }
      ]
    },
    {
      ...taxBurdenResponse,
      tax_breakdown: [
        {
          ...taxBurdenResponse.tax_breakdown[0],
          label: "   "
        }
      ]
    },
    {
      ...taxBurdenResponse,
      tax_breakdown: [
        taxBurdenResponse.tax_breakdown[0],
        {
          ...taxBurdenResponse.tax_breakdown[0],
          label: "Duplicate federal income tax",
          amount: "0.00"
        }
      ]
    },
    {
      ...taxBurdenResponse,
      tax_breakdown: [
        {
          ...taxBurdenResponse.tax_breakdown[0],
          amount: "NaN"
        }
      ]
    }
  ])("rejects malformed tax burden responses", async (body) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status: 200
      })
    );

    await expect(fetchTaxBurden(calculateRequest)).rejects.toMatchObject({
      message: "Malformed tax burden response"
    });
  });

  test("returns valid income series responses", async () => {
    const body = { rows: [taxBurdenResponse] };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status: 200
      })
    );

    await expect(fetchIncomeSeries(seriesRequest)).resolves.toEqual(body);
  });

  test.each([
    {},
    { rows: [] },
    { rows: taxBurdenResponse },
    { rows: [{ ...taxBurdenResponse, marginal_employee_tax_rate: "oops" }] }
  ])("rejects malformed income series responses", async (body) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status: 200
      })
    );

    await expect(fetchIncomeSeries(seriesRequest)).rejects.toMatchObject({
      message: "Malformed income series response"
    });
  });
});
