import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  Calculator,
  Database,
  LineChart,
  RefreshCw,
  ShieldCheck
} from "lucide-react";
import {
  fetchFilingStatuses,
  fetchIncomeSeries,
  fetchTaxParameters,
  fetchTaxYears
} from "./api";
import type { FilingStatus, TaxBurden, TaxParameters } from "./types";

type ChartRow = TaxBurden & {
  incomeNumber: number;
  totalTaxNumber: number;
  totalPretaxDeductionsNumber: number;
  totalTaxRatePercent: number;
  marginalTaxRatePercent: number;
};

type ChartMode = "effectiveRate" | "marginalRate" | "totalTax";
type PretaxDeductionMode = "max_available" | "gradual_phase_in";

type CurveSeries = {
  key: string;
  label: string;
  color: string;
  rows: ChartRow[];
};

type ComparisonChartPoint = {
  incomeNumber: number;
} & Record<string, number | null>;

type ChartTooltipPayloadEntry = {
  color?: string;
  dataKey?: string | number;
  name?: string | number;
  payload?: Record<string, number | null | undefined>;
};

type ChartPointValue = {
  value: number;
  totalRate: number;
  totalTax: number;
  marginal: number;
  pretax: number;
};

type ChartTooltipProps = {
  active?: boolean;
  chartMode: ChartMode;
  label?: string | number;
  payload?: readonly ChartTooltipPayloadEntry[];
};

type ChartClickState = {
  activeLabel?: unknown;
  activePayload?: Array<{
    payload?: {
      incomeNumber?: unknown;
    };
  }>;
};

const SERIES_COLORS = [
  "#237a5b",
  "#5966a8",
  "#a65f2b",
  "#8a4f94",
  "#4b7f8f",
  "#8c6d1f",
  "#b04a54",
  "#526b2f"
];

function toCurrency(value: string | number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0
  }).format(Number(value));
}

function toPercent(value: string | number): string {
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function formatPercentValue(value: string | number): string {
  return `${Number(value).toFixed(2)}%`;
}

function trimTrailingZeros(value: string): string {
  return value.replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1");
}

function formatIncomeAxisTick(value: string | number): string {
  const amount = Number(value);
  if (Math.abs(amount) >= 500000) {
    return `$${trimTrailingZeros((amount / 1000000).toFixed(1))}m`;
  }
  return `$${trimTrailingZeros((amount / 1000).toFixed(0))}k`;
}

function thousandsToDollars(value: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "0";
  return trimTrailingZeros((amount * 1000).toFixed(2));
}

function dollarsToThousands(value: string | number): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "0";
  return trimTrailingZeros((amount / 1000).toFixed(3));
}

function formatThousandsOption(value: string | number): string {
  return `$${dollarsToThousands(value)}k`;
}

function seriesColor(index: number): string {
  return SERIES_COLORS[index % SERIES_COLORS.length];
}

function seriesKey(year: number, filingStatus: string): string {
  return `curve_${year}_${filingStatus.replace(/[^a-z0-9]+/gi, "_")}`;
}

function chartPayloadKeys(key: string) {
  return {
    marginal: `${key}_marginal`,
    pretax: `${key}_pretax`,
    totalRate: `${key}_total_rate`,
    totalTax: `${key}_total_tax`
  };
}

function chartValue(row: ChartRow, chartMode: ChartMode): number {
  if (chartMode === "marginalRate") return row.marginalTaxRatePercent;
  if (chartMode === "totalTax") return row.totalTaxNumber;
  return row.totalTaxRatePercent;
}

function chartPointValue(row: ChartRow, chartMode: ChartMode): ChartPointValue {
  return {
    value: chartValue(row, chartMode),
    totalRate: row.totalTaxRatePercent,
    totalTax: row.totalTaxNumber,
    marginal: row.marginalTaxRatePercent,
    pretax: row.totalPretaxDeductionsNumber
  };
}

function chartValueAtIncome(
  rows: ChartRow[],
  income: number,
  chartMode: ChartMode
): ChartPointValue | null {
  let low = 0;
  let high = rows.length - 1;

  while (low <= high) {
    const midpoint = Math.floor((low + high) / 2);
    const row = rows[midpoint];
    if (row.incomeNumber === income) return chartPointValue(row, chartMode);
    if (row.incomeNumber < income) {
      low = midpoint + 1;
    } else {
      high = midpoint - 1;
    }
  }

  const lower = rows[high];
  const upper = rows[low];
  if (!lower || !upper) return null;

  const progress =
    (income - lower.incomeNumber) / (upper.incomeNumber - lower.incomeNumber);
  const totalTax =
    lower.totalTaxNumber +
    (upper.totalTaxNumber - lower.totalTaxNumber) * progress;
  const pretax =
    lower.totalPretaxDeductionsNumber +
    (upper.totalPretaxDeductionsNumber - lower.totalPretaxDeductionsNumber) *
      progress;
  const totalRate = income === 0 ? 0 : (totalTax / income) * 100;
  const marginal = lower.marginalTaxRatePercent;

  return {
    value:
      chartMode === "totalTax"
        ? totalTax
        : chartMode === "marginalRate"
          ? marginal
          : totalRate,
    totalRate,
    totalTax,
    marginal,
    pretax
  };
}

function additionalMedicareThreshold(parameters: TaxParameters): number {
  return Number(
    parameters.payroll.additional_medicare_thresholds[
      parameters.federal.filing_status
    ] ?? parameters.payroll.additional_medicare_threshold_single
  );
}

function marginalRateChangeIncomes(
  parameters: TaxParameters,
  mode: PretaxDeductionMode
): number[] {
  const pretaxCap = totalPretaxDeductionCap(parameters);
  const standardDeduction = Number(parameters.federal.standard_deduction);
  const incomes: number[] = [];

  if (mode === "max_available") {
    if (pretaxCap > 0) incomes.push(pretaxCap);
    for (const bracket of parameters.federal.brackets) {
      incomes.push(
        standardDeduction + pretaxCap + Number(bracket.lower_bound)
      );
    }
  } else {
    incomes.push(standardDeduction);
    incomes.push(gradualPhaseInEnd(parameters));
    for (const bracket of parameters.federal.brackets.slice(1)) {
      const income = solveIncomeForTarget(
        Number(bracket.lower_bound),
        (grossIncome) =>
          taxableIncomeBeforeTax(parameters, mode, grossIncome)
      );
      if (income !== null) incomes.push(income);
    }
  }

  for (const payrollThreshold of [
    Number(parameters.payroll.social_security_wage_base),
    additionalMedicareThreshold(parameters)
  ]) {
    const income = solveIncomeForTarget(
      payrollThreshold,
      (grossIncome) => payrollWages(parameters, mode, grossIncome)
    );
    if (income !== null) incomes.push(income);
  }

  return incomes
    .filter((income) => Number.isFinite(income))
    .map(roundMoneyNumber);
}

function totalPretaxDeductionCap(parameters: TaxParameters): number {
  return (
    Number(parameters.pretax_deductions.employee_401k_limit) +
    Number(parameters.pretax_deductions.health_fsa_limit) +
    Number(parameters.pretax_deductions.dependent_care_fsa_limit)
  );
}

function gradualPhaseInEnd(parameters: TaxParameters): number {
  const nextToLastBracket =
    parameters.federal.brackets[
      Math.max(0, parameters.federal.brackets.length - 2)
    ];
  return (
    Number(parameters.federal.standard_deduction) +
    Number(nextToLastBracket?.lower_bound ?? 0) +
    totalPretaxDeductionCap(parameters)
  );
}

function pretaxDeductionsAtIncome(
  parameters: TaxParameters,
  mode: PretaxDeductionMode,
  grossIncome: number
) {
  const totalCap = totalPretaxDeductionCap(parameters);
  if (totalCap <= 0) return { total: 0, healthFsa: 0 };

  let total: number;
  if (mode === "max_available") {
    total = Math.min(grossIncome, totalCap);
  } else if (grossIncome <= Number(parameters.federal.standard_deduction)) {
    total = 0;
  } else {
    const phaseStart = Number(parameters.federal.standard_deduction);
    const phaseEnd = gradualPhaseInEnd(parameters);
    const z = Math.max(
      0,
      Math.min(1, (grossIncome - phaseStart) / (phaseEnd - phaseStart))
    );
    const startRate = Number(
      parameters.pretax_deductions.gradual_phase_in_start_rate
    );
    const endRate = totalCap / phaseEnd;
    total = Math.min(totalCap, grossIncome * (startRate + (endRate - startRate) * z));
  }

  return {
    total,
    healthFsa:
      (total * Number(parameters.pretax_deductions.health_fsa_limit)) / totalCap
  };
}

function taxableIncomeBeforeTax(
  parameters: TaxParameters,
  mode: PretaxDeductionMode,
  grossIncome: number
): number {
  const pretax = pretaxDeductionsAtIncome(parameters, mode, grossIncome);
  return Math.max(
    0,
    grossIncome - pretax.total - Number(parameters.federal.standard_deduction)
  );
}

function payrollWages(
  parameters: TaxParameters,
  mode: PretaxDeductionMode,
  grossIncome: number
): number {
  const pretax = pretaxDeductionsAtIncome(parameters, mode, grossIncome);
  return Math.max(0, grossIncome - pretax.healthFsa);
}

function solveIncomeForTarget(
  target: number,
  valueAtIncome: (grossIncome: number) => number
): number | null {
  if (target < 0) return null;

  let lower = 0;
  let upper = Math.max(1, target);
  while (valueAtIncome(upper) < target) {
    upper *= 2;
    if (upper > 1000000000) return null;
  }

  for (let index = 0; index < 80; index += 1) {
    const midpoint = (lower + upper) / 2;
    if (valueAtIncome(midpoint) < target) {
      lower = midpoint;
    } else {
      upper = midpoint;
    }
  }

  return roundMoneyNumber(upper);
}

function roundMoneyNumber(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function sortedUniqueNumbers(values: Iterable<number>): number[] {
  return [...new Set(values)].sort((left, right) => left - right);
}

function defaultStopThousands(
  parameters: TaxParameters,
  mode: PretaxDeductionMode
): string {
  const lastChangeIncome = Math.max(
    ...marginalRateChangeIncomes(parameters, mode)
  );
  return dollarsToThousands(lastChangeIncome * 1.1);
}

function buildChartRows(
  rows: TaxBurden[],
  includeEmployer: boolean
): ChartRow[] {
  return rows.map((row) => {
    const incomeNumber = Number(row.gross_income);
    const totalTaxNumber = includeEmployer
      ? Number(row.total_tax_with_employer_payroll)
      : Number(row.total_employee_tax);
    const totalPretaxDeductionsNumber = Number(row.total_pretax_deductions);
    const marginalTaxRate = includeEmployer
      ? Number(row.marginal_tax_rate_with_employer_payroll)
      : Number(row.marginal_employee_tax_rate);

    return {
      ...row,
      incomeNumber,
      totalTaxNumber,
      totalPretaxDeductionsNumber,
      totalTaxRatePercent:
        incomeNumber === 0 ? 0 : (totalTaxNumber / incomeNumber) * 100,
      marginalTaxRatePercent: marginalTaxRate * 100
    };
  });
}

function comparisonSeriesLabel(
  year: number,
  statusLabel: string,
  compareFilingStatuses: boolean,
  compareTaxYears: boolean
): string {
  if (compareFilingStatuses && compareTaxYears) return `${year} ${statusLabel}`;
  if (compareTaxYears) return `${year} ${statusLabel}`;
  return statusLabel;
}

function breakdownShare(amount: string, totalTax: number): number {
  if (totalTax <= 0) return 0;
  return Math.max(0, Math.min(100, (Number(amount) / totalTax) * 100));
}

function nearestRow(rows: ChartRow[], income: number): ChartRow | undefined {
  return rows.reduce<ChartRow | undefined>((nearest, row) => {
    if (!nearest) return row;
    return Math.abs(row.incomeNumber - income) <
      Math.abs(nearest.incomeNumber - income)
      ? row
      : nearest;
  }, undefined);
}

function readClickedIncome(state: unknown): number | null {
  if (!state || typeof state !== "object") return null;
  const chartState = state as ChartClickState;
  const income = Number(
    chartState.activePayload?.[0]?.payload?.incomeNumber ??
      chartState.activeLabel
  );
  return Number.isFinite(income) ? income : null;
}

function marginalRateChangeIncomeSet(
  parameters: TaxParameters | null,
  mode: PretaxDeductionMode,
  start: string,
  stop: string
): Set<number> {
  const startAmount = Number(start) || 0;
  const stopAmount = Number(stop) || 0;
  const incomes = new Set<number>([startAmount]);
  if (!parameters) return incomes;

  for (const income of marginalRateChangeIncomes(parameters, mode)) {
    incomes.add(income);
  }

  return new Set(
    [...incomes].filter((income) => income >= startAmount && income <= stopAmount)
  );
}

function ChartTooltip({
  active,
  chartMode,
  label,
  payload = []
}: ChartTooltipProps) {
  if (!active || payload.length === 0) return null;

  return (
    <div className="chart-tooltip">
      <strong>Income {toCurrency(label ?? 0)}</strong>
      <ol>
        {payload.map((entry) => {
          const key = String(entry.dataKey ?? "");
          const keys = chartPayloadKeys(key);
          const point = entry.payload ?? {};
          const totalRate = point[keys.totalRate];
          const marginalRate = point[keys.marginal];
          const totalTax = point[keys.totalTax];
          const pretax = point[keys.pretax];

          return (
            <li key={key}>
              <span className="tooltip-series">
                <i style={{ backgroundColor: entry.color }} />
                {entry.name}
              </span>
              {chartMode === "totalTax" ? (
                <span>Total tax {toCurrency(totalTax ?? 0)}</span>
              ) : null}
              <span>Total rate {formatPercentValue(totalRate ?? 0)}</span>
              <span>Marginal rate {formatPercentValue(marginalRate ?? 0)}</span>
              <span>Pre-tax deductions {toCurrency(pretax ?? 0)}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function App() {
  const [taxYears, setTaxYears] = useState<number[]>([]);
  const [filingStatuses, setFilingStatuses] = useState<FilingStatus[]>([]);
  const [year, setYear] = useState(2026);
  const [filingStatus, setFilingStatus] = useState("single");
  const [startThousands, setStartThousands] = useState("0");
  const [stopThousands, setStopThousands] = useState("");
  const [hasCustomStop, setHasCustomStop] = useState(false);
  const [stepThousands, setStepThousands] = useState("10");
  const [selectedIncome, setSelectedIncome] = useState(100000);
  const [includeEmployer, setIncludeEmployer] = useState(false);
  const [pretaxDeductionMode, setPretaxDeductionMode] =
    useState<PretaxDeductionMode>("max_available");
  const [compareFilingStatuses, setCompareFilingStatuses] = useState(false);
  const [compareTaxYears, setCompareTaxYears] = useState(false);
  const [chartMode, setChartMode] = useState<ChartMode>("effectiveRate");
  const [parameters, setParameters] = useState<TaxParameters | null>(null);
  const [rows, setRows] = useState<TaxBurden[]>([]);
  const [comparisonSeries, setComparisonSeries] = useState<CurveSeries[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const start = thousandsToDollars(startThousands);
  const stop = thousandsToDollars(stopThousands);
  const step = thousandsToDollars(stepThousands);
  const selectedFilingStatus = filingStatuses.find(
    (status) => status.code === filingStatus
  );

  useEffect(() => {
    fetchTaxYears()
      .then((years) => {
        setTaxYears(years);
        if (years.length > 0) {
          setYear(years[years.length - 1]);
        }
      })
      .catch((nextError: Error) => setError(nextError.message));
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchFilingStatuses(year)
      .then((statuses) => {
        if (cancelled) return;
        setFilingStatuses(statuses);
        if (!statuses.some((status) => status.code === filingStatus)) {
          setFilingStatus(statuses[0]?.code ?? "single");
        }
      })
      .catch((nextError: Error) => {
        if (!cancelled) setError(nextError.message);
      });

    return () => {
      cancelled = true;
    };
  }, [year, filingStatus]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    async function loadScenario() {
      const nextParameters = await fetchTaxParameters(year, filingStatus);
      const nextDefaultStopThousands = defaultStopThousands(
        nextParameters,
        pretaxDeductionMode
      );
      const resolvedStop = hasCustomStop
        ? stop
        : thousandsToDollars(nextDefaultStopThousands);
      const selectedSeriesRequest = {
        year,
        filingStatus,
        start,
        stop: resolvedStop,
        step,
        includeEmployerPayrollTax: includeEmployer,
        includeMarginalBreakpoints: true,
        pretaxDeductionMode
      };
      const selectedSeries = await fetchIncomeSeries(selectedSeriesRequest);
      const yearsToCompare =
        compareTaxYears && taxYears.length > 0 ? taxYears : [year];
      const seriesRequests: Array<{
        year: number;
        filingStatus: string;
        statusLabel: string;
      }> = [];

      for (const comparisonYear of yearsToCompare) {
        const statuses =
          comparisonYear === year && filingStatuses.length > 0
            ? filingStatuses
            : await fetchFilingStatuses(comparisonYear);
        const statusesToCompare = compareFilingStatuses
          ? statuses
          : statuses.filter((status) => status.code === filingStatus);

        for (const status of statusesToCompare) {
          seriesRequests.push({
            year: comparisonYear,
            filingStatus: status.code,
            statusLabel: status.label
          });
        }
      }

      if (seriesRequests.length === 0) {
        seriesRequests.push({
          year,
          filingStatus,
          statusLabel: selectedFilingStatus?.label ?? filingStatus
        });
      }

      const nextComparisonSeries = await Promise.all(
        seriesRequests.map(async (request, index) => {
          const isSelectedSeries =
            request.year === year && request.filingStatus === filingStatus;
          const response = isSelectedSeries
            ? selectedSeries
            : await fetchIncomeSeries({
                ...selectedSeriesRequest,
                year: request.year,
                filingStatus: request.filingStatus
              });

          return {
            key: seriesKey(request.year, request.filingStatus),
            label: comparisonSeriesLabel(
              request.year,
              request.statusLabel,
              compareFilingStatuses,
              compareTaxYears
            ),
            color: seriesColor(index),
            rows: buildChartRows(response.rows, includeEmployer)
          };
        })
      );

      if (cancelled) return;
      if (!hasCustomStop && stopThousands !== nextDefaultStopThousands) {
        setStopThousands(nextDefaultStopThousands);
      }
      setParameters(nextParameters);
      setRows(selectedSeries.rows);
      setComparisonSeries(nextComparisonSeries);
    }

    loadScenario()
      .catch((nextError: Error) => {
        if (cancelled) return;
        setComparisonSeries([]);
        setError(nextError.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [
    year,
    filingStatus,
    selectedFilingStatus?.label,
    start,
    stop,
    step,
    stopThousands,
    hasCustomStop,
    includeEmployer,
    pretaxDeductionMode,
    compareFilingStatuses,
    compareTaxYears,
    taxYears,
    filingStatuses
  ]);

  const chartRows = useMemo<ChartRow[]>(
    () => buildChartRows(rows, includeEmployer),
    [rows, includeEmployer]
  );

  const selectedRow = useMemo(
    () => nearestRow(chartRows, selectedIncome),
    [chartRows, selectedIncome]
  );

  const tableRows = useMemo(() => {
    const breakpointIncomes = marginalRateChangeIncomeSet(
      parameters,
      pretaxDeductionMode,
      start,
      stop
    );
    return chartRows.filter((row) => breakpointIncomes.has(row.incomeNumber));
  }, [chartRows, parameters, pretaxDeductionMode, start, stop]);

  const sampledIncomeOptions = useMemo(
    () => sortedUniqueNumbers(tableRows.map((row) => row.incomeNumber)),
    [tableRows]
  );

  const quickStartOptions = useMemo(
    () => sortedUniqueNumbers([0, ...sampledIncomeOptions]),
    [sampledIncomeOptions]
  );

  const quickStopOptions = useMemo(
    () => sampledIncomeOptions.filter((income) => income > 0),
    [sampledIncomeOptions]
  );

  const comparisonChartData = useMemo<ComparisonChartPoint[]>(() => {
    const incomes = new Set<number>();
    for (const series of comparisonSeries) {
      for (const row of series.rows) {
        incomes.add(row.incomeNumber);
      }
    }

    return sortedUniqueNumbers(incomes).map((income) => {
      const point = { incomeNumber: income } as ComparisonChartPoint;
      for (const series of comparisonSeries) {
        const keys = chartPayloadKeys(series.key);
        const values = chartValueAtIncome(series.rows, income, chartMode);
        point[series.key] = values?.value ?? null;
        point[keys.totalRate] = values?.totalRate ?? null;
        point[keys.totalTax] = values?.totalTax ?? null;
        point[keys.marginal] = values?.marginal ?? null;
        point[keys.pretax] = values?.pretax ?? null;
      }
      return point;
    });
  }, [comparisonSeries, chartMode]);

  const selectedAdditionalMedicareThreshold =
    parameters ? additionalMedicareThreshold(parameters) : undefined;
  const chartLabel =
    chartMode === "marginalRate"
      ? "Marginal tax rate"
      : chartMode === "totalTax"
        ? "Total tax paid"
        : "Effective tax rate";
  const curveType = chartMode === "marginalRate" ? "stepAfter" : "monotone";
  const comparingCurves = compareFilingStatuses || compareTaxYears;
  const dataStatusLabel = loading
    ? "Loading"
    : comparingCurves
      ? `${comparisonSeries.length} ${
          comparisonSeries.length === 1 ? "curve" : "curves"
        }`
      : `${chartRows.length} rows`;
  const primarySeries = comparisonSeries[0];
  const breakdownRows = selectedRow?.tax_breakdown ?? [];
  const totalBreakdownTax = selectedRow?.totalTaxNumber ?? 0;
  const handleChartClick = (state: unknown) => {
    const income = readClickedIncome(state);
    if (income !== null) {
      setSelectedIncome(income);
    }
  };
  const setQuickStart = (income: number) => {
    setStartThousands(dollarsToThousands(income));
    setSelectedIncome((currentIncome) => Math.max(currentIncome, income));
  };
  const setQuickStop = (income: number) => {
    setHasCustomStop(true);
    setStopThousands(dollarsToThousands(income));
    setSelectedIncome((currentIncome) => Math.min(currentIncome, income));
  };

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div className="brand">
          <div className="brand-mark">
            <Calculator size={22} aria-hidden="true" />
          </div>
          <div>
            <h1>Tax Explorer</h1>
            <p>2026 federal W-2 income with pre-tax deduction modeling</p>
          </div>
        </div>
        <div className="status-pill" title="Parameters loaded from SQLite">
          <Database size={16} aria-hidden="true" />
          <span>SQLite-backed {year}</span>
        </div>
      </header>

      <section className="workspace">
        <aside className="control-panel" aria-label="Tax scenario controls">
          <div className="panel-heading">
            <LineChart size={18} aria-hidden="true" />
            <h2>Scenario</h2>
          </div>

          <label>
            <span>Tax year</span>
            <select
              value={year}
              onChange={(event) => setYear(Number(event.target.value))}
            >
              {taxYears.map((taxYear) => (
                <option key={taxYear} value={taxYear}>
                  {taxYear}
                </option>
              ))}
            </select>
          </label>

          <div className="segmented-field">
            <span id="filing-status-label">Filing status</span>
            <div
              className="segmented-control filing-status-control"
              role="radiogroup"
              aria-labelledby="filing-status-label"
            >
              {filingStatuses.map((status) => (
                <button
                  key={status.code}
                  type="button"
                  role="radio"
                  aria-checked={status.code === filingStatus}
                  className={status.code === filingStatus ? "active" : ""}
                  onClick={() => setFilingStatus(status.code)}
                >
                  {status.label}
                </button>
              ))}
            </div>
          </div>

          <div className="field-grid">
            <div className="range-field">
              <label htmlFor="start-thousands">
                <span>Start ($k)</span>
              </label>
              <input
                id="start-thousands"
                type="number"
                min="0"
                step="0.001"
                value={startThousands}
                onChange={(event) => setStartThousands(event.target.value)}
              />
              <select
                aria-label="Quick start"
                value=""
                onChange={(event) => {
                  if (event.target.value) {
                    setQuickStart(Number(event.target.value));
                  }
                }}
              >
                <option value="">Quick start</option>
                {quickStartOptions.map((income) => (
                  <option key={income} value={income}>
                    {formatThousandsOption(income)}
                  </option>
                ))}
              </select>
            </div>
            <div className="range-field">
              <label htmlFor="stop-thousands">
                <span>Stop ($k)</span>
              </label>
              <input
                id="stop-thousands"
                type="number"
                min="0"
                step="0.001"
                value={stopThousands}
                onChange={(event) => {
                  setHasCustomStop(true);
                  setStopThousands(event.target.value);
                }}
              />
              <select
                aria-label="Quick stop"
                value=""
                onChange={(event) => {
                  if (event.target.value) {
                    setQuickStop(Number(event.target.value));
                  }
                }}
              >
                <option value="">Quick stop</option>
                {quickStopOptions.map((income) => (
                  <option key={income} value={income}>
                    {formatThousandsOption(income)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <label>
            <span>Step ($k)</span>
            <input
              type="number"
              min="1"
              value={stepThousands}
              onChange={(event) => setStepThousands(event.target.value)}
            />
          </label>

          <label>
            <span>Selected income</span>
            <input
              type="range"
              min={Number(start) || 0}
              max={Number(stop) || 0}
              step={Number(step) || 1000}
              value={selectedIncome}
              onChange={(event) => setSelectedIncome(Number(event.target.value))}
            />
            <strong>{toCurrency(selectedIncome)}</strong>
          </label>

          <label className="toggle-row">
            <input
              type="checkbox"
              checked={includeEmployer}
              onChange={(event) => setIncludeEmployer(event.target.checked)}
            />
            <span>Employer payroll taxes</span>
          </label>

          <div className="segmented-field">
            <span id="deduction-mode-label">Deductions</span>
            <div
              className="segmented-control deduction-mode-control"
              role="radiogroup"
              aria-labelledby="deduction-mode-label"
            >
              <button
                type="button"
                role="radio"
                aria-checked={pretaxDeductionMode === "max_available"}
                className={
                  pretaxDeductionMode === "max_available" ? "active" : ""
                }
                onClick={() => setPretaxDeductionMode("max_available")}
              >
                Max available
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={pretaxDeductionMode === "gradual_phase_in"}
                className={
                  pretaxDeductionMode === "gradual_phase_in" ? "active" : ""
                }
                onClick={() => setPretaxDeductionMode("gradual_phase_in")}
              >
                Gradual phase-in
              </button>
            </div>
          </div>

          <div className="mode-control" aria-label="Chart Y-axis mode">
            <span>Chart value</span>
            <div>
              <button
                type="button"
                className={chartMode === "effectiveRate" ? "active" : ""}
                onClick={() => setChartMode("effectiveRate")}
              >
                Effective Rate
              </button>
              <button
                type="button"
                className={chartMode === "marginalRate" ? "active" : ""}
                onClick={() => setChartMode("marginalRate")}
              >
                Marginal Rate
              </button>
              <button
                type="button"
                className={chartMode === "totalTax" ? "active" : ""}
                onClick={() => setChartMode("totalTax")}
              >
                Total Tax $
              </button>
            </div>
          </div>

          <div className="compare-control">
            <span>Compare curves</span>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={compareFilingStatuses}
                onChange={(event) =>
                  setCompareFilingStatuses(event.target.checked)
                }
              />
              <span>All filing statuses</span>
            </label>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={compareTaxYears}
                onChange={(event) => setCompareTaxYears(event.target.checked)}
              />
              <span>All tax years</span>
            </label>
          </div>

          <button
            type="button"
            className="refresh-button"
            onClick={() => setSelectedIncome(Number(start) || 0)}
            title="Reset selected income"
          >
            <RefreshCw size={16} aria-hidden="true" />
            Reset
          </button>
        </aside>

        <section className="results-panel">
          <div className="chart-header">
            <div>
              <h2>Tax Burden Curve</h2>
              <p>
                {chartLabel}; federal income tax plus W-2 payroll taxes
              </p>
            </div>
            <div className="data-status">
              <ShieldCheck size={16} aria-hidden="true" />
              <span>{dataStatusLabel}</span>
            </div>
          </div>

          {error ? <div className="error-box">{error}</div> : null}

          <div className="chart-frame">
            <ResponsiveContainer width="100%" height={360}>
              <ComposedChart
                data={comparisonChartData}
                margin={{ left: 8, right: 12 }}
                onClick={handleChartClick}
              >
                <CartesianGrid stroke="#e7e4dc" vertical={false} />
                <XAxis
                  dataKey="incomeNumber"
                  type="number"
                  domain={[Number(start) || 0, Number(stop) || "dataMax"]}
                  tickFormatter={formatIncomeAxisTick}
                  stroke="#706b60"
                  minTickGap={24}
                />
                <YAxis
                  tickFormatter={(value) =>
                    chartMode === "totalTax"
                      ? `$${Number(value) / 1000}k`
                      : `${Number(value).toFixed(0)}%`
                  }
                  stroke="#706b60"
                />
                <Tooltip
                  content={(props) => (
                    <ChartTooltip
                      active={props.active}
                      chartMode={chartMode}
                      label={props.label}
                      payload={
                        props.payload as unknown as readonly ChartTooltipPayloadEntry[]
                      }
                    />
                  )}
                />
                {comparingCurves ? (
                  <>
                    <Legend verticalAlign="top" height={34} />
                    {comparisonSeries.map((series) => (
                      <Line
                        key={series.key}
                        type={curveType}
                        dataKey={series.key}
                        name={series.label}
                        stroke={series.color}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4 }}
                        connectNulls
                      />
                    ))}
                  </>
                ) : primarySeries ? (
                  <Area
                    type={curveType}
                    dataKey={primarySeries.key}
                    fill="#d9eadf"
                    stroke={primarySeries.color}
                    fillOpacity={0.65}
                    name={primarySeries.label}
                  />
                ) : null}
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="summary-strip">
            <Metric
              label="Gross income"
              value={selectedRow ? toCurrency(selectedRow.gross_income) : "-"}
            />
            <Metric
              label="Taxable income"
              value={selectedRow ? toCurrency(selectedRow.taxable_income) : "-"}
            />
            <Metric
              label="Federal income tax"
              value={
                selectedRow ? toCurrency(selectedRow.federal_income_tax) : "-"
              }
            />
            <Metric
              label="Employee payroll tax"
              value={
                selectedRow
                  ? toCurrency(selectedRow.total_employee_payroll_tax)
                  : "-"
              }
            />
            <Metric
              label="Pre-tax deductions"
              value={
                selectedRow
                  ? toCurrency(selectedRow.total_pretax_deductions)
                  : "-"
              }
            />
            <Metric
              label="Effective rate"
              value={
                selectedRow
                  ? formatPercentValue(selectedRow.totalTaxRatePercent)
                  : "-"
              }
            />
          </div>

          <section
            className="breakdown-section"
            aria-label="Tax paid by type"
          >
            <div className="breakdown-heading">
              <Calculator size={18} aria-hidden="true" />
              <div>
                <h3>Tax Breakdown</h3>
                <p>
                  Selected income{" "}
                  {selectedRow ? toCurrency(selectedRow.gross_income) : "-"}
                </p>
              </div>
            </div>
            {breakdownRows.length > 0 ? (
              <ol className="breakdown-list">
                {breakdownRows.map((item) => {
                  const share = breakdownShare(item.amount, totalBreakdownTax);
                  return (
                    <li key={item.code} className="breakdown-row">
                      <div className="breakdown-row-top">
                        <span>{item.label}</span>
                        <strong>{toCurrency(item.amount)}</strong>
                      </div>
                      <div className="breakdown-track" aria-hidden="true">
                        <div style={{ width: `${share}%` }} />
                      </div>
                      <small>
                        {formatPercentValue(share)} of selected total tax
                      </small>
                    </li>
                  );
                })}
              </ol>
            ) : (
              <p className="breakdown-empty">No tax components available.</p>
            )}
          </section>
        </section>
      </section>

      <section className="detail-grid">
        <section className="parameter-panel">
          <h2>Tax Parameters</h2>
          {parameters ? (
            <>
              <dl>
                <div>
                  <dt>Filing status</dt>
                  <dd>
                    {selectedFilingStatus?.label ??
                      parameters.federal.filing_status}
                  </dd>
                </div>
                <div>
                  <dt>Standard deduction</dt>
                  <dd>{toCurrency(parameters.federal.standard_deduction)}</dd>
                </div>
                <div>
                  <dt>Social Security wage base</dt>
                  <dd>
                    {toCurrency(parameters.payroll.social_security_wage_base)}
                  </dd>
                </div>
                <div>
                  <dt>Additional Medicare threshold</dt>
                  <dd>
                    {toCurrency(selectedAdditionalMedicareThreshold ?? "0")}
                  </dd>
                </div>
                <div>
                  <dt>401(k) limit</dt>
                  <dd>
                    {toCurrency(
                      parameters.pretax_deductions.employee_401k_limit
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Health FSA limit</dt>
                  <dd>
                    {toCurrency(parameters.pretax_deductions.health_fsa_limit)}
                  </dd>
                </div>
                <div>
                  <dt>Dependent-care FSA limit</dt>
                  <dd>
                    {toCurrency(
                      parameters.pretax_deductions.dependent_care_fsa_limit
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Phase-in start rate</dt>
                  <dd>
                    {toPercent(
                      parameters.pretax_deductions.gradual_phase_in_start_rate
                    )}
                  </dd>
                </div>
              </dl>
              <table>
                <thead>
                  <tr>
                    <th>Bracket starts</th>
                    <th>Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {parameters.federal.brackets.map((bracket) => (
                    <tr key={bracket.lower_bound}>
                      <td>{toCurrency(bracket.lower_bound)}</td>
                      <td>{toPercent(bracket.rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : null}
        </section>

        <section className="table-panel">
          <h2>Sampled Income Rows</h2>
          <table>
            <thead>
              <tr>
                <th>Income</th>
                <th>Pre-tax deductions</th>
                <th>401(k)</th>
                <th>Health FSA</th>
                <th>Income tax</th>
                <th>Social Security</th>
                <th>Medicare</th>
                <th>Addl Medicare</th>
                {includeEmployer ? <th>Employer payroll</th> : null}
                <th>Total</th>
                <th>Effective rate</th>
                <th>Marginal rate</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((row) => (
                <tr key={row.gross_income}>
                  <td>{toCurrency(row.gross_income)}</td>
                  <td>{toCurrency(row.total_pretax_deductions)}</td>
                  <td>{toCurrency(row.employee_401k_contribution)}</td>
                  <td>{toCurrency(row.health_fsa_contribution)}</td>
                  <td>{toCurrency(row.federal_income_tax)}</td>
                  <td>{toCurrency(row.employee_social_security_tax)}</td>
                  <td>{toCurrency(row.employee_medicare_tax)}</td>
                  <td>{toCurrency(row.employee_additional_medicare_tax)}</td>
                  {includeEmployer ? (
                    <td>{toCurrency(row.total_employer_payroll_tax)}</td>
                  ) : null}
                  <td>{toCurrency(row.totalTaxNumber)}</td>
                  <td>{formatPercentValue(row.totalTaxRatePercent)}</td>
                  <td>{formatPercentValue(row.marginalTaxRatePercent)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default App;
