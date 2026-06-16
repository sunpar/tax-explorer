import type { ReactNode } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import type {
  FilingStatus,
  IncomeSeriesResponse,
  TaxBurden,
  TaxParameters
} from "./types";
import {
  fetchTaxBurden,
  fetchFilingStatuses,
  fetchIncomeSeries,
  fetchTaxParameters,
  fetchTaxYears
} from "./api";

vi.mock("./api", () => ({
  fetchTaxBurden: vi.fn(),
  fetchFilingStatuses: vi.fn(),
  fetchIncomeSeries: vi.fn(),
  fetchTaxParameters: vi.fn(),
  fetchTaxYears: vi.fn()
}));

vi.mock("recharts", async () => {
  const ReactModule = await import("react");
  const React = ReactModule.default;

  type ChartPoint = Record<string, number | null | undefined>;
  type ChartChild = ReactNode;

  function collectSeries(children: ChartChild): Array<{
    color?: string;
    dataKey: string;
    name?: string;
  }> {
    const series: Array<{ color?: string; dataKey: string; name?: string }> = [];

    ReactModule.Children.forEach(children, (child) => {
      if (!ReactModule.isValidElement(child)) return;
      const props = child.props as {
        children?: ChartChild;
        dataKey?: string;
        name?: string;
        stroke?: string;
      };
      if (props.dataKey && props.name) {
        series.push({
          color: props.stroke,
          dataKey: props.dataKey,
          name: props.name
        });
      }
      if (props.children) {
        series.push(...collectSeries(props.children));
      }
    });

    return series;
  }

  function renderTooltip(children: ChartChild, data: ChartPoint[]) {
    const point =
      data.find((entry) => entry.incomeNumber === 100000) ?? data[0] ?? {};
    const series = collectSeries(children);

    return ReactModule.Children.map(children, (child) => {
      if (!ReactModule.isValidElement(child)) return child;
      const props = child.props as {
        content?: (props: unknown) => ReactNode;
      };
      if (!props.content) return child;

      return props.content({
        active: true,
        label: point.incomeNumber,
        payload: series.map((entry) => ({
          color: entry.color,
          dataKey: entry.dataKey,
          name: entry.name,
          payload: point
        }))
      });
    });
  }

  return {
    Area: (props: Record<string, unknown>) =>
      React.createElement("div", {
        "data-testid": "area",
        "data-key": props.dataKey,
        "data-name": props.name
      }),
    CartesianGrid: () => null,
    ComposedChart: ({
      children,
      data,
      onClick
    }: {
      children: ChartChild;
      data: ChartPoint[];
      onClick?: (state: unknown) => void;
    }) =>
      React.createElement(
        "div",
        {
          "data-testid": "chart",
          "data-chart-data": JSON.stringify(data),
          onClick: () =>
            onClick?.({
              activePayload: [{ payload: { incomeNumber: 50000 } }]
            })
        },
        renderTooltip(children, data)
      ),
    Legend: () => React.createElement("div", { "data-testid": "legend" }),
    Line: (props: Record<string, unknown>) =>
      React.createElement("div", {
        "data-testid": "line",
        "data-key": props.dataKey,
        "data-name": props.name
      }),
    ResponsiveContainer: ({ children }: { children: ChartChild }) =>
      React.createElement(React.Fragment, null, children),
    Tooltip: () => null,
    XAxis: (props: Record<string, unknown>) =>
      React.createElement("div", {
        "data-testid": "x-axis",
        "data-domain": JSON.stringify(props.domain),
        "data-type": props.type
      }),
    YAxis: () => null
  };
});

const statuses: FilingStatus[] = [
  { code: "single", label: "Single" },
  { code: "married_joint", label: "Married filing jointly" }
];

const singleParameters = taxParameters("single", "100000");
const marriedParameters = taxParameters("married_joint", "250000");

const mockFetchTaxYears = vi.mocked(fetchTaxYears);
const mockFetchFilingStatuses = vi.mocked(fetchFilingStatuses);
const mockFetchTaxParameters = vi.mocked(fetchTaxParameters);
const mockFetchIncomeSeries = vi.mocked(fetchIncomeSeries);
const mockFetchTaxBurden = vi.mocked(fetchTaxBurden);

function taxParameters(
  filingStatus: string,
  additionalMedicareThreshold: string
): TaxParameters {
  return {
    federal: {
      tax_year: 2026,
      filing_status: filingStatus,
      standard_deduction: "0.00",
      brackets: [
        { lower_bound: "0.00", rate: "0.10" },
        { lower_bound: "50000.00", rate: "0.22" },
        { lower_bound: "100000.00", rate: "0.24" }
      ]
    },
    payroll: {
      tax_year: 2026,
      social_security_rate: "0.062",
      social_security_wage_base: "80000.00",
      medicare_rate: "0.0145",
      additional_medicare_rate: "0.009",
      additional_medicare_threshold_single: "100000.00",
      additional_medicare_thresholds: {
        [filingStatus]: additionalMedicareThreshold
      }
    },
    pretax_deductions: {
      tax_year: 2026,
      employee_401k_limit: "24500.00",
      health_fsa_limit: "3400.00",
      dependent_care_fsa_limit: "7500.00",
      gradual_phase_in_start_rate: "0.01"
    }
  };
}

function taxBurden(
  income: number,
  filingStatus: string,
  dependentCount = 0,
  secondaryIncome = 0,
  includeEmployerPayrollTax = false
): TaxBurden {
  const married = filingStatus === "married_joint";
  const totalTax = married ? income * 0.15 : income * 0.2;
  const marginalRate = married ? "0.2000" : "0.3000";
  const dependentCare = dependentCount > 0 ? "7500.00" : "0.00";
  const dualIncome = married && secondaryIncome > 0;
  const employee401k = dualIncome ? "49000.00" : "24500.00";
  const healthFsa = dualIncome ? "6800.00" : "3400.00";
  const totalPretaxDeductions = dualIncome
    ? dependentCount > 0
      ? "63300.00"
      : "55800.00"
    : dependentCount > 0
      ? "35400.00"
      : "27900.00";
  const employerSocialSecurityTax =
    includeEmployerPayrollTax && dualIncome ? "18178.40" : "0.00";
  const employerMedicareTax =
    includeEmployerPayrollTax && dualIncome ? "4251.40" : "0.00";
  const totalEmployerPayrollTax =
    includeEmployerPayrollTax && dualIncome ? "22429.80" : "0.00";
  const payrollBreakdown =
    includeEmployerPayrollTax && dualIncome
      ? [
          {
            label: "Income 1",
            gross_income: "150000.00",
            payroll_wages: "146600.00",
            employee_social_security_tax: "9089.20",
            employee_medicare_tax: "2125.70",
            employee_additional_medicare_tax: "194.40",
            total_employee_payroll_tax: "11409.30",
            employer_social_security_tax: "9089.20",
            employer_medicare_tax: "2125.70",
            total_employer_payroll_tax: "11214.90",
            total_payroll_tax: "22624.20"
          },
          {
            label: "Income 2",
            gross_income: "150000.00",
            payroll_wages: "146600.00",
            employee_social_security_tax: "9089.20",
            employee_medicare_tax: "2125.70",
            employee_additional_medicare_tax: "194.40",
            total_employee_payroll_tax: "11409.30",
            employer_social_security_tax: "9089.20",
            employer_medicare_tax: "2125.70",
            total_employer_payroll_tax: "11214.90",
            total_payroll_tax: "22624.20"
          },
          {
            label: "Total",
            gross_income: "300000.00",
            payroll_wages: "293200.00",
            employee_social_security_tax: "18178.40",
            employee_medicare_tax: "4251.40",
            employee_additional_medicare_tax: "388.80",
            total_employee_payroll_tax: "22818.60",
            employer_social_security_tax: "18178.40",
            employer_medicare_tax: "4251.40",
            total_employer_payroll_tax: "22429.80",
            total_payroll_tax: "45248.40"
          }
        ]
      : [
          {
            label: "Total",
            gross_income: income.toFixed(2),
            payroll_wages: income.toFixed(2),
            employee_social_security_tax: "0.00",
            employee_medicare_tax: "0.00",
            employee_additional_medicare_tax: "0.00",
            total_employee_payroll_tax: "0.00",
            employer_social_security_tax: "0.00",
            employer_medicare_tax: "0.00",
            total_employer_payroll_tax: "0.00",
            total_payroll_tax: "0.00"
          }
        ];

  return {
    gross_income: income.toFixed(2),
    taxable_income: income.toFixed(2),
    federal_income_tax: (income * (married ? 0.075 : 0.1)).toFixed(2),
    employee_social_security_tax: "0.00",
    employee_medicare_tax: "0.00",
    employee_additional_medicare_tax: "0.00",
    total_employee_payroll_tax: "0.00",
    total_employee_tax: totalTax.toFixed(2),
    effective_employee_tax_rate: married ? "0.1500" : "0.2000",
    marginal_employee_tax_rate: marginalRate,
    employee_401k_contribution: employee401k,
    health_fsa_contribution: healthFsa,
    dependent_care_fsa_contribution: dependentCare,
    total_pretax_deductions: totalPretaxDeductions,
    employer_social_security_tax: employerSocialSecurityTax,
    employer_medicare_tax: employerMedicareTax,
    total_employer_payroll_tax: totalEmployerPayrollTax,
    total_tax_with_employer_payroll: (
      totalTax + Number(totalEmployerPayrollTax)
    ).toFixed(2),
    marginal_tax_rate_with_employer_payroll: marginalRate,
    payroll_breakdown: payrollBreakdown,
    tax_breakdown: [
      {
        code: "federal_income_tax",
        label: "Federal income tax",
        amount: (income * (married ? 0.075 : 0.1)).toFixed(2)
      },
      ...(includeEmployerPayrollTax && dualIncome
        ? [
            {
              code: "employer_social_security_tax",
              label: "Employer Social Security tax",
              amount: employerSocialSecurityTax
            },
            {
              code: "employer_medicare_tax",
              label: "Employer Medicare tax",
              amount: employerMedicareTax
            }
          ]
        : [])
    ]
  };
}

function incomeSeries(
  filingStatus: string,
  dependentCount = 0,
  secondaryIncome = 0
): IncomeSeriesResponse {
  const incomes =
    filingStatus === "married_joint" && secondaryIncome > 0
      ? [0, 55800, 91100, 105800, 155800, 186160, 256800]
      : dependentCount > 0
        ? [0, 35400, 85400, 90900, 110900, 135400]
      : [0, 27900, 77900, 83400, 100000, 103400, 127900];

  return {
    rows: incomes.map((income) =>
      taxBurden(income, filingStatus, dependentCount, secondaryIncome)
    )
  };
}

function chartData(): Array<Record<string, number | null>> {
  return JSON.parse(screen.getByTestId("chart").dataset.chartData ?? "[]") as Array<
    Record<string, number | null>
  >;
}

async function renderLoadedApp(expectedStop = 140.69, expectedSelected = 127900) {
  render(<App />);
  await screen.findByRole("heading", { name: "Tax Burden Curve" });
  await waitFor(() =>
    expect(screen.getByLabelText("Stop ($k)")).toHaveValue(expectedStop)
  );
  await waitFor(() =>
    expect(screen.getByLabelText(/Selected income/)).toHaveValue(
      String(expectedSelected)
    )
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  mockFetchTaxYears.mockResolvedValue([2026]);
  mockFetchFilingStatuses.mockResolvedValue(statuses);
  mockFetchTaxParameters.mockImplementation(async (_year, filingStatus) =>
    filingStatus === "married_joint" ? marriedParameters : singleParameters
  );
  mockFetchIncomeSeries.mockImplementation(async (request) =>
    incomeSeries(
      request.filingStatus,
      request.dependentCount,
      Number(request.secondaryIncome)
    )
  );
  mockFetchTaxBurden.mockImplementation(async (request) =>
    taxBurden(
      Number(request.grossIncome),
      request.filingStatus,
      request.dependentCount,
      Number(request.secondaryIncome),
      request.includeEmployerPayrollTax
    )
  );
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("App tax curve controls", () => {
  test("defaults Stop to 10 percent above the last marginal-rate change and preserves custom Stop", async () => {
    await renderLoadedApp();

    expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
      expect.objectContaining({
        filingStatus: "single",
        dependentCount: 0,
        secondaryIncome: "0",
        pretaxDeductionMode: "gradual_phase_in",
        stop: "140690"
      })
    );

    const stopInput = screen.getByLabelText("Stop ($k)");
    fireEvent.change(stopInput, { target: { value: "75" } });

    await waitFor(() =>
      expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
        expect.objectContaining({
          filingStatus: "single",
          dependentCount: 0,
          secondaryIncome: "0",
          pretaxDeductionMode: "gradual_phase_in",
          stop: "75000"
        })
      )
    );

    fireEvent.click(screen.getByRole("radio", { name: "Married filing jointly" }));

    await waitFor(() =>
      expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
        expect.objectContaining({
          filingStatus: "married_joint",
          dependentCount: 0,
          secondaryIncome: "0",
          pretaxDeductionMode: "gradual_phase_in",
          stop: "75000"
        })
      )
    );
    expect(stopInput).toHaveValue(75);
  });

  test("quick range buttons update Start and Stop", async () => {
    await renderLoadedApp();

    expect(screen.queryByLabelText("Quick start")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Quick stop")).not.toBeInTheDocument();

    const startPresets = screen.getByText("Start presets").closest("details");
    const stopPresets = screen.getByText("Stop presets").closest("details");
    expect(startPresets).not.toBeNull();
    expect(stopPresets).not.toBeNull();
    expect(startPresets).not.toHaveAttribute("open");
    expect(stopPresets).not.toHaveAttribute("open");

    fireEvent.click(screen.getByText("Start presets"));
    expect(startPresets).toHaveAttribute("open");

    fireEvent.click(screen.getByRole("button", { name: "Start $77.9k" }));

    expect(screen.getByLabelText("Start ($k)")).toHaveValue(77.9);
    await waitFor(() =>
      expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
        expect.objectContaining({
          start: "77900"
        })
      )
    );

    fireEvent.click(screen.getByText("Stop presets"));
    expect(stopPresets).toHaveAttribute("open");

    fireEvent.click(screen.getByRole("button", { name: "Stop $83.4k" }));

    expect(screen.getByLabelText("Stop ($k)")).toHaveValue(83.4);
    expect(screen.getByLabelText(/Selected income/)).toHaveValue("83400");
    await waitFor(() =>
      expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
        expect.objectContaining({
          stop: "83400"
        })
      )
    );
  });

  test("chart click updates the selected income", async () => {
    await renderLoadedApp();

    const selectedIncome = screen.getByLabelText(/Selected income/);
    expect(selectedIncome).toHaveValue("127900");
    expect(selectedIncome).toHaveAttribute("step", "1");
    expect(selectedIncome).toHaveAttribute("max", "3000000");

    fireEvent.click(screen.getByTestId("chart"));

    expect(selectedIncome).toHaveValue("50000");
  });

  test("selected income slider supports exact calculations up to $3m", async () => {
    await renderLoadedApp();

    fireEvent.change(screen.getByLabelText(/Selected income/), {
      target: { value: "3000000" }
    });

    await waitFor(() =>
      expect(mockFetchTaxBurden).toHaveBeenCalledWith(
        expect.objectContaining({
          grossIncome: "3000000"
        })
      )
    );
    expect(screen.getByLabelText(/Selected income/)).toHaveValue("3000000");
    expect(screen.getAllByText("$3,000,000").length).toBeGreaterThan(0);
  });

  test("clears selected income calculation errors after a successful retry", async () => {
    await renderLoadedApp();
    mockFetchTaxBurden.mockRejectedValueOnce(
      new Error("temporary calculation failure")
    );

    fireEvent.change(screen.getByLabelText(/Selected income/), {
      target: { value: "120000" }
    });

    expect(
      await screen.findByText("temporary calculation failure")
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Selected income/), {
      target: { value: "130000" }
    });

    await waitFor(() =>
      expect(mockFetchTaxBurden).toHaveBeenCalledWith(
        expect.objectContaining({
          grossIncome: "130000"
        })
      )
    );
    await waitFor(() =>
      expect(
        screen.queryByText("temporary calculation failure")
      ).not.toBeInTheDocument()
    );
  });

  test("comparison chart modes plot effective, marginal, and total-tax values with tooltip detail", async () => {
    await renderLoadedApp();

    fireEvent.click(screen.getByLabelText("All filing statuses"));

    await waitFor(() => expect(screen.getByText("2 curves")).toBeInTheDocument());
    expect(screen.getByTestId("x-axis")).toHaveAttribute("data-type", "number");
    expect(screen.getByTestId("x-axis")).toHaveAttribute(
      "data-domain",
      "[0,140690]"
    );
    const seriesNames = screen
      .getAllByTestId("line")
      .map((line) => line.dataset.name);
    expect(seriesNames).toContain("Single");
    expect(seriesNames).toContain("Married filing jointly");

    let income100k = chartData().find((point) => point.incomeNumber === 100000);
    expect(income100k?.curve_2026_single).toBe(20);
    expect(income100k?.curve_2026_married_joint).toBe(15);
    const income77900 = chartData().find((point) => point.incomeNumber === 77900);
    expect(income77900?.curve_2026_single).toBe(20);
    const income83400 = chartData().find((point) => point.incomeNumber === 83400);
    expect(income83400?.curve_2026_married_joint).toBe(15);
    expect(screen.getAllByText("Total tax $20,000").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Effective rate 20.00%").length).toBeGreaterThan(
      0
    );

    fireEvent.click(screen.getByRole("button", { name: "Marginal Rate" }));
    await waitFor(() =>
      expect(
        screen.getByText(
          "Marginal tax rate; federal income tax plus W-2 payroll taxes"
        )
      ).toBeInTheDocument()
    );
    income100k = chartData().find((point) => point.incomeNumber === 100000);
    expect(income100k?.curve_2026_single).toBe(30);
    expect(income100k?.curve_2026_married_joint).toBe(20);
    expect(screen.getAllByText("Marginal rate 30.00%").length).toBeGreaterThan(
      0
    );
    expect(screen.getAllByText("Total tax $20,000").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Total Tax $" }));
    await waitFor(() =>
      expect(
        screen.getByText(
          "Total tax paid; federal income tax plus W-2 payroll taxes"
        )
      ).toBeInTheDocument()
    );
    income100k = chartData().find((point) => point.incomeNumber === 100000);
    expect(income100k?.curve_2026_single).toBe(20000);
    expect(income100k?.curve_2026_married_joint).toBe(15000);

    const tooltip = screen.getByText("Income $100,000").closest(".chart-tooltip");
    expect(tooltip).not.toBeNull();
    expect(
      within(tooltip as HTMLElement).getByText("Total tax $20,000")
    ).toBeInTheDocument();
    expect(
      within(tooltip as HTMLElement).getByText("Effective rate 20.00%")
    ).toBeInTheDocument();
    expect(
      within(tooltip as HTMLElement).getByText("Marginal rate 30.00%")
    ).toBeInTheDocument();
    expect(
      within(tooltip as HTMLElement).getAllByText(
        "Pre-tax deductions $27,900"
      ).length
    ).toBeGreaterThan(0);
  });

  test("deduction mode selector defaults to gradual phase-in and can request max available", async () => {
    await renderLoadedApp();

    expect(screen.getByText("Gradual phase-in")).toHaveClass("active");
    expect(screen.getAllByText("Pre-tax deductions").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$27,900").length).toBeGreaterThan(0);
    expect(screen.getByText("Deduction Usage")).toBeInTheDocument();
    expect(screen.getByText("401(k) contribution")).toBeInTheDocument();
    expect(screen.getByText("Health FSA contribution")).toBeInTheDocument();
    expect(screen.getByText("Dependent-care FSA")).toBeInTheDocument();
    expect(
      screen.getByText("100.00% of $27,900 max")
    ).toBeInTheDocument();
    expect(
      screen.getByText("100.00% of $24,500 max")
    ).toBeInTheDocument();
    expect(
      screen.getByText("100.00% of $3,400 max")
    ).toBeInTheDocument();
    expect(screen.getByText("No dependents ($7,500 max)")).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Dependent care" })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Max available" }));

    await waitFor(() =>
      expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
        expect.objectContaining({
          pretaxDeductionMode: "max_available"
        })
      )
    );
    expect(screen.getByText("Max available")).toHaveClass("active");
    expect(screen.getByText("401(k) limit")).toBeInTheDocument();
    expect(screen.getByText("Health FSA limit")).toBeInTheDocument();
  });

  test("dependents input is saved and sent with income-series requests", async () => {
    await renderLoadedApp();

    const dependentsInput = screen.getByLabelText("Dependents");
    expect(dependentsInput).toHaveValue(0);

    fireEvent.change(dependentsInput, { target: { value: "2" } });

    await waitFor(() =>
      expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
        expect.objectContaining({
          dependentCount: 2
        })
      )
    );
    expect(localStorage.getItem("taxExplorer.dependentCount")).toBe("2");
    expect(screen.getAllByText("$35,400").length).toBeGreaterThan(0);
    expect(
      screen.getByText("100.00% of $35,400 max")
    ).toBeInTheDocument();
    expect(
      screen.getByText("100.00% of $7,500 max")
    ).toBeInTheDocument();

    cleanup();
    await renderLoadedApp(148.94, 135400);

    expect(screen.getByLabelText("Dependents")).toHaveValue(2);
    await waitFor(() =>
      expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
        expect.objectContaining({
          dependentCount: 2
        })
      )
    );
  });

  test("married joint secondary income is saved and sent with requests", async () => {
    await renderLoadedApp();

    expect(screen.queryByLabelText("Income 2 ($k)")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Married filing jointly" }));

    const income1Input = await screen.findByLabelText("Income 1 ($k)");
    const income2Input = screen.getByLabelText("Income 2 ($k)");
    await waitFor(() =>
      expect(screen.getByLabelText(/Selected income/)).toHaveValue("256800")
    );
    await waitFor(() => {
      expect(income1Input).toHaveValue(154.08);
      expect(income2Input).toHaveValue(102.72);
    });

    fireEvent.change(income2Input, { target: { value: "50" } });

    await waitFor(() =>
      expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
        expect.objectContaining({
          filingStatus: "married_joint",
          secondaryIncome: "50000"
        })
      )
    );
    expect(localStorage.getItem("taxExplorer.secondaryIncomeThousands")).toBe(
      "50"
    );
    expect(localStorage.getItem("taxExplorer.primaryIncomeThousands")).toBe(
      "154.08"
    );
    expect(screen.getByLabelText(/Selected income/)).toHaveValue("204080");
    expect(screen.getAllByText("$55,800").length).toBeGreaterThan(0);
    expect(
      screen.getByText("100.00% of $49,000 max")
    ).toBeInTheDocument();
    expect(
      screen.getByText("100.00% of $6,800 max")
    ).toBeInTheDocument();
  });

  test("married joint income split is saved and restored", async () => {
    await renderLoadedApp();

    fireEvent.click(screen.getByRole("radio", { name: "Married filing jointly" }));

    const income1Input = await screen.findByLabelText("Income 1 ($k)");
    const income2Input = screen.getByLabelText("Income 2 ($k)");

    fireEvent.change(income1Input, { target: { value: "514.02" } });
    fireEvent.change(income2Input, { target: { value: "342.68" } });

    await waitFor(() =>
      expect(screen.getByLabelText(/Selected income/)).toHaveValue("856700")
    );
    expect(localStorage.getItem("taxExplorer.primaryIncomeThousands")).toBe(
      "514.02"
    );
    expect(localStorage.getItem("taxExplorer.secondaryIncomeThousands")).toBe(
      "342.68"
    );

    cleanup();
    await renderLoadedApp();

    fireEvent.click(screen.getByRole("radio", { name: "Married filing jointly" }));

    await waitFor(() =>
      expect(screen.getByLabelText(/Selected income/)).toHaveValue("856700")
    );
    expect(screen.getByLabelText("Income 1 ($k)")).toHaveValue(514.02);
    expect(screen.getByLabelText("Income 2 ($k)")).toHaveValue(342.68);
    await waitFor(() =>
      expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
        expect.objectContaining({
          filingStatus: "married_joint",
          secondaryIncome: "342680"
        })
      )
    );
  });

  test("stored two-income mode defaults selected income to sampled max and splits 60/40", async () => {
    localStorage.setItem("taxExplorer.secondaryIncomeThousands", "1");
    await renderLoadedApp();

    fireEvent.click(screen.getByRole("radio", { name: "Married filing jointly" }));

    await waitFor(() =>
      expect(screen.getByLabelText(/Selected income/)).toHaveValue("256800")
    );
    await waitFor(() => {
      expect(screen.getByLabelText("Income 1 ($k)")).toHaveValue(154.08);
      expect(screen.getByLabelText("Income 2 ($k)")).toHaveValue(102.72);
    });
    await waitFor(() =>
      expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
        expect.objectContaining({
          filingStatus: "married_joint",
          secondaryIncome: "102720"
        })
      )
    );
  });

  test("employer payroll toggle shows dual-earner employer and payroll breakdown", async () => {
    await renderLoadedApp();

    fireEvent.click(screen.getByRole("radio", { name: "Married filing jointly" }));

    const income1Input = await screen.findByLabelText("Income 1 ($k)");
    const income2Input = screen.getByLabelText("Income 2 ($k)");
    fireEvent.change(income1Input, { target: { value: "150" } });
    fireEvent.change(income2Input, { target: { value: "150" } });
    fireEvent.click(screen.getByLabelText("Employer payroll taxes"));

    const payrollSection = await screen.findByRole("region", {
      name: "Employer payroll tax details"
    });
    expect(
      within(payrollSection).getByText("Employer Payroll Breakdown")
    ).toBeInTheDocument();
    expect(
      within(payrollSection).getByText("Employer-paid payroll tax")
    ).toBeInTheDocument();
    expect(
      within(payrollSection).getByText("Combined payroll tax")
    ).toBeInTheDocument();
    expect(within(payrollSection).getAllByText("$22,430").length).toBeGreaterThan(
      0
    );
    expect(within(payrollSection).getAllByText("$45,248").length).toBeGreaterThan(
      0
    );
    expect(within(payrollSection).getByText("Income 1")).toBeInTheDocument();
    expect(within(payrollSection).getByText("Income 2")).toBeInTheDocument();
    expect(
      within(payrollSection).getAllByText("$11,215").length
    ).toBeGreaterThanOrEqual(2);
  });
});
