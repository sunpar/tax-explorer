import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
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
};

type ChartMode = "rate" | "absolute";

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

function App() {
  const [taxYears, setTaxYears] = useState<number[]>([]);
  const [filingStatuses, setFilingStatuses] = useState<FilingStatus[]>([]);
  const [year, setYear] = useState(2026);
  const [filingStatus, setFilingStatus] = useState("single");
  const [start, setStart] = useState("0");
  const [stop, setStop] = useState("500000");
  const [step, setStep] = useState("10000");
  const [selectedIncome, setSelectedIncome] = useState(100000);
  const [includeEmployer, setIncludeEmployer] = useState(false);
  const [chartMode, setChartMode] = useState<ChartMode>("rate");
  const [parameters, setParameters] = useState<TaxParameters | null>(null);
  const [rows, setRows] = useState<TaxBurden[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

    Promise.all([
      fetchTaxParameters(year, filingStatus),
      fetchIncomeSeries({
        year,
        filingStatus,
        start,
        stop,
        step,
        includeEmployerPayrollTax: includeEmployer
      })
    ])
      .then(([nextParameters, series]) => {
        if (cancelled) return;
        setParameters(nextParameters);
        setRows(series.rows);
      })
      .catch((nextError: Error) => {
        if (!cancelled) setError(nextError.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [year, filingStatus, start, stop, step, includeEmployer]);

  const chartRows = useMemo<ChartRow[]>(
    () =>
      rows.map((row) => {
        const incomeNumber = Number(row.gross_income);
        const totalTaxNumber = includeEmployer
          ? Number(row.total_tax_with_employer_payroll)
          : Number(row.total_employee_tax);

        return {
          ...row,
          incomeNumber,
          totalTaxNumber,
          totalTaxRatePercent:
            incomeNumber === 0 ? 0 : (totalTaxNumber / incomeNumber) * 100
        };
      }),
    [rows, includeEmployer]
  );

  const selectedRow = useMemo(
    () => nearestRow(chartRows, selectedIncome),
    [chartRows, selectedIncome]
  );

  const tableRows = useMemo(() => {
    if (chartRows.length <= 12) return chartRows;
    const stride = Math.ceil(chartRows.length / 12);
    return chartRows.filter((_, index) => index % stride === 0);
  }, [chartRows]);

  const selectedFilingStatus = filingStatuses.find(
    (status) => status.code === filingStatus
  );
  const chartDataKey =
    chartMode === "rate" ? "totalTaxRatePercent" : "totalTaxNumber";
  const chartLabel =
    chartMode === "rate" ? "Total tax as % of W-2 income" : "Total tax paid";
  const breakdownRows = selectedRow?.tax_breakdown ?? [];
  const totalBreakdownTax = selectedRow?.totalTaxNumber ?? 0;

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

          <label>
            <span>Filing status</span>
            <select
              value={filingStatus}
              onChange={(event) => setFilingStatus(event.target.value)}
            >
              {filingStatuses.map((status) => (
                <option key={status.code} value={status.code}>
                  {status.label}
                </option>
              ))}
            </select>
          </label>

          <div className="field-grid">
            <label>
              <span>Start</span>
              <input
                type="number"
                min="0"
                value={start}
                onChange={(event) => setStart(event.target.value)}
              />
            </label>
            <label>
              <span>Stop</span>
              <input
                type="number"
                min="0"
                value={stop}
                onChange={(event) => setStop(event.target.value)}
              />
            </label>
          </div>

          <label>
            <span>Step</span>
            <input
              type="number"
              min="1"
              value={step}
              onChange={(event) => setStep(event.target.value)}
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
                className={chartMode === "rate" ? "active" : ""}
                onClick={() => setChartMode("rate")}
              >
                Percent
              </button>
              <button
                type="button"
                className={chartMode === "absolute" ? "active" : ""}
                onClick={() => setChartMode("absolute")}
              >
                Dollars
              </button>
            </div>
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
              <span>{loading ? "Loading" : `${chartRows.length} rows`}</span>
            </div>
          </div>

          {error ? <div className="error-box">{error}</div> : null}

          <div className="chart-frame">
            <ResponsiveContainer width="100%" height={360}>
              <ComposedChart data={chartRows} margin={{ left: 8, right: 12 }}>
                <CartesianGrid stroke="#e7e4dc" vertical={false} />
                <XAxis
                  dataKey="incomeNumber"
                  tickFormatter={(value) => `$${Number(value) / 1000}k`}
                  stroke="#706b60"
                  minTickGap={24}
                />
                <YAxis
                  tickFormatter={(value) =>
                    chartMode === "rate"
                      ? `${Number(value).toFixed(0)}%`
                      : `$${Number(value) / 1000}k`
                  }
                  stroke="#706b60"
                />
                <Tooltip
                  formatter={(value) => {
                    if (chartMode === "rate") {
                      return [
                        `${Number(value).toFixed(2)}%`,
                        "Total tax rate"
                      ];
                    }
                    return [toCurrency(Number(value)), "Total tax paid"];
                  }}
                  labelFormatter={(value) => `Income ${toCurrency(Number(value))}`}
                />
                <Area
                  type="monotone"
                  dataKey={chartDataKey}
                  fill="#d9eadf"
                  stroke="#237a5b"
                  fillOpacity={0.65}
                  name={chartDataKey}
                />
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
                    {toCurrency(
                      parameters.payroll.additional_medicare_threshold_single
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
                <th>Income tax</th>
                <th>Social Security</th>
                <th>Medicare</th>
                <th>Addl Medicare</th>
                {includeEmployer ? <th>Employer payroll</th> : null}
                <th>Total</th>
                <th>Rate</th>
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
