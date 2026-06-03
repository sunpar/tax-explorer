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
  totalTaxRatePercent: number;
  marginalTaxRatePercent: number;
};

type ChartMode = "effectiveRate" | "marginalRate" | "totalTax";

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
    totalRate: `${key}_total_rate`,
    totalTax: `${key}_total_tax`
  };
}

function chartValue(row: ChartRow, chartMode: ChartMode): number {
  if (chartMode === "marginalRate") return row.marginalTaxRatePercent;
  if (chartMode === "totalTax") return row.totalTaxNumber;
  return row.totalTaxRatePercent;
}

function additionalMedicareThreshold(parameters: TaxParameters): number {
  return Number(
    parameters.payroll.additional_medicare_thresholds[
      parameters.federal.filing_status
    ] ?? parameters.payroll.additional_medicare_threshold_single
  );
}

function marginalRateChangeIncomes(parameters: TaxParameters): number[] {
  const incomes = parameters.federal.brackets.map(
    (bracket) =>
      Number(parameters.federal.standard_deduction) +
      Number(bracket.lower_bound)
  );
  incomes.push(Number(parameters.payroll.social_security_wage_base));
  incomes.push(additionalMedicareThreshold(parameters));
  return incomes.filter((income) => Number.isFinite(income));
}

function defaultStopThousands(parameters: TaxParameters): string {
  const lastChangeIncome = Math.max(...marginalRateChangeIncomes(parameters));
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
    const marginalTaxRate = includeEmployer
      ? Number(row.marginal_tax_rate_with_employer_payroll)
      : Number(row.marginal_employee_tax_rate);

    return {
      ...row,
      incomeNumber,
      totalTaxNumber,
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
  start: string,
  stop: string
): Set<number> {
  const startAmount = Number(start) || 0;
  const stopAmount = Number(stop) || 0;
  const incomes = new Set<number>([startAmount]);
  if (!parameters) return incomes;

  for (const income of marginalRateChangeIncomes(parameters)) {
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
      const nextDefaultStopThousands = defaultStopThousands(nextParameters);
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
        includeMarginalBreakpoints: true
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
    const breakpointIncomes = marginalRateChangeIncomeSet(parameters, start, stop);
    return chartRows.filter((row) => breakpointIncomes.has(row.incomeNumber));
  }, [chartRows, parameters, start, stop]);

  const sampledIncomeOptions = useMemo(
    () =>
      [...new Set(tableRows.map((row) => row.incomeNumber))].sort(
        (left, right) => left - right
      ),
    [tableRows]
  );

  const quickStartOptions = useMemo(
    () =>
      [...new Set([0, ...sampledIncomeOptions])].sort(
        (left, right) => left - right
      ),
    [sampledIncomeOptions]
  );

  const quickStopOptions = useMemo(
    () => sampledIncomeOptions.filter((income) => income > 0),
    [sampledIncomeOptions]
  );

  const comparisonChartData = useMemo<ComparisonChartPoint[]>(() => {
    const points = new Map<number, ComparisonChartPoint>();

    for (const series of comparisonSeries) {
      for (const row of series.rows) {
        const point =
          points.get(row.incomeNumber) ?? ({ incomeNumber: row.incomeNumber } as ComparisonChartPoint);
        const keys = chartPayloadKeys(series.key);
        point[series.key] = chartValue(row, chartMode);
        point[keys.totalRate] = row.totalTaxRatePercent;
        point[keys.totalTax] = row.totalTaxNumber;
        point[keys.marginal] = row.marginalTaxRatePercent;
        points.set(row.incomeNumber, point);
      }
    }

    return [...points.values()].sort(
      (left, right) => left.incomeNumber - right.incomeNumber
    );
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
            <p>2026 federal W-2 income, standard deduction only</p>
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
                  <dd>{selectedFilingStatus?.label ?? parameters.federal.filing_status}</dd>
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
