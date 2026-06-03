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
  fetchFilingStatuses,
  fetchIncomeSeries,
  fetchTaxParameters,
  fetchTaxYears
} from "./api";

vi.mock("./api", () => ({
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
      dependent_care_fsa_limit: "0.00",
      gradual_phase_in_start_rate: "0.01"
    }
  };
}

function taxBurden(income: number, filingStatus: string): TaxBurden {
  const married = filingStatus === "married_joint";
  const totalTax = married ? income * 0.15 : income * 0.2;
  const marginalRate = married ? "0.2000" : "0.3000";

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
    employee_401k_contribution: "24500.00",
    health_fsa_contribution: "3400.00",
    dependent_care_fsa_contribution: "0.00",
    total_pretax_deductions: "27900.00",
    employer_social_security_tax: "0.00",
    employer_medicare_tax: "0.00",
    total_employer_payroll_tax: "0.00",
    total_tax_with_employer_payroll: totalTax.toFixed(2),
    marginal_tax_rate_with_employer_payroll: marginalRate,
    tax_breakdown: [
      {
        code: "federal_income_tax",
        label: "Federal income tax",
        amount: (income * (married ? 0.075 : 0.1)).toFixed(2)
      }
    ]
  };
}

function incomeSeries(filingStatus: string): IncomeSeriesResponse {
  const incomes =
    filingStatus === "married_joint"
      ? [0, 50000, 75000, 100000, 110000]
      : [0, 50000, 80000, 100000, 110000];

  return {
    rows: incomes.map((income) => taxBurden(income, filingStatus))
  };
}

function chartData(): Array<Record<string, number | null>> {
  return JSON.parse(screen.getByTestId("chart").dataset.chartData ?? "[]") as Array<
    Record<string, number | null>
  >;
}

async function renderLoadedApp() {
  render(<App />);
  await screen.findByRole("heading", { name: "Tax Burden Curve" });
  await waitFor(() =>
    expect(screen.getByLabelText("Stop ($k)")).toHaveValue(140.69)
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockFetchTaxYears.mockResolvedValue([2026]);
  mockFetchFilingStatuses.mockResolvedValue(statuses);
  mockFetchTaxParameters.mockImplementation(async (_year, filingStatus) =>
    filingStatus === "married_joint" ? marriedParameters : singleParameters
  );
  mockFetchIncomeSeries.mockImplementation(async (request) =>
    incomeSeries(request.filingStatus)
  );
});

afterEach(() => {
  cleanup();
});

describe("App tax curve controls", () => {
  test("defaults Stop to 10 percent above the last marginal-rate change and preserves custom Stop", async () => {
    await renderLoadedApp();

    expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
      expect.objectContaining({
        filingStatus: "single",
        pretaxDeductionMode: "max_available",
        stop: "140690"
      })
    );

    const stopInput = screen.getByLabelText("Stop ($k)");
    fireEvent.change(stopInput, { target: { value: "75" } });

    await waitFor(() =>
      expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
        expect.objectContaining({
          filingStatus: "single",
          pretaxDeductionMode: "max_available",
          stop: "75000"
        })
      )
    );

    fireEvent.click(screen.getByRole("radio", { name: "Married filing jointly" }));

    await waitFor(() =>
      expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
        expect.objectContaining({
          filingStatus: "married_joint",
          pretaxDeductionMode: "max_available",
          stop: "75000"
        })
      )
    );
    expect(stopInput).toHaveValue(75);
  });

  test("chart click updates the selected income", async () => {
    await renderLoadedApp();

    const selectedIncome = screen.getByLabelText(/Selected income/);
    expect(selectedIncome).toHaveValue("100000");

    fireEvent.click(screen.getByTestId("chart"));

    expect(selectedIncome).toHaveValue("50000");
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
    const income75k = chartData().find((point) => point.incomeNumber === 75000);
    expect(income75k?.curve_2026_single).toBe(20);
    const income80k = chartData().find((point) => point.incomeNumber === 80000);
    expect(income80k?.curve_2026_married_joint).toBe(15);

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
      within(tooltip as HTMLElement).getByText("Total rate 20.00%")
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

  test("deduction mode selector requests gradual phase-in and displays deductions", async () => {
    await renderLoadedApp();

    expect(screen.getByText("Max available")).toHaveClass("active");
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
    expect(screen.getByText("Inactive ($0 cap)")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Gradual phase-in" }));

    await waitFor(() =>
      expect(mockFetchIncomeSeries).toHaveBeenCalledWith(
        expect.objectContaining({
          pretaxDeductionMode: "gradual_phase_in"
        })
      )
    );
    expect(screen.getByText("Gradual phase-in")).toHaveClass("active");
    expect(screen.getByText("401(k) limit")).toBeInTheDocument();
    expect(screen.getByText("Health FSA limit")).toBeInTheDocument();
  });
});
