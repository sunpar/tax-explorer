import { useEffect, useMemo, useRef, useState } from "react";
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
  fetchTaxBurden,
  fetchFilingStatuses,
  fetchIncomeSeries,
  fetchTaxParameters,
  fetchTaxYears
} from "./api";
import type { FilingStatus, TaxBurden, TaxParameters } from "./types";

type ChartRow = TaxBurden & {
  isMarginalBreakpoint: boolean;
  incomeNumber: number;
  totalTaxNumber: number;
  totalPretaxDeductionsNumber: number;
  totalTaxRatePercent: number;
  marginalTaxRatePercent: number;
};

type ChartMode = "effectiveRate" | "marginalRate" | "totalTax";
type PretaxDeductionMode = "max_available" | "gradual_phase_in";

type PretaxDeductionCaps = {
  employee401k: number;
  healthFsa: number;
  dependentCareFsa: number;
  total: number;
};

type DeductionUsageItem = {
  label: string;
  amount: string;
  cap: number;
  inactiveLabel?: string;
};

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
const DEPENDENT_COUNT_STORAGE_KEY = "taxExplorer.dependentCount";
const PRIMARY_INCOME_STORAGE_KEY = "taxExplorer.primaryIncomeThousands";
const SECONDARY_INCOME_STORAGE_KEY = "taxExplorer.secondaryIncomeThousands";
const DEFAULT_TAX_YEAR = 2026;
const SELECTED_INCOME_MAX_FLOOR = 3000000;
const SELECTED_INCOME_LINEAR_RANGE_LIMIT = 10000000;
const DEFAULT_STEP_THOUSANDS = "10";
const DEFAULT_STEP_DOLLARS = 10000;
const MAX_MONEY_NUMBER = 1e26;
const MAX_AUTOMATIC_STOP = MAX_MONEY_NUMBER * (1 - Number.EPSILON);
const MAX_INCOME_SERIES_ROWS = 2001;

function sanitizeDependentCount(value: string | number | null): number {
  if (typeof value === "string" && !/^\d+$/.test(value)) return 0;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 0;
}

function readStoredDependentCount(): string {
  if (typeof window === "undefined") return "0";
  return String(
    sanitizeDependentCount(window.localStorage.getItem(DEPENDENT_COUNT_STORAGE_KEY))
  );
}

function sanitizeThousandsValue(value: string | number | null): string {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount <= 0) return "0";
  return trimTrailingZeros(amount.toFixed(3));
}

function sanitizeStoredPrimaryIncomeThousands(value: string): string | null {
  if (value.trim() === "") return null;
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0) return null;
  return trimTrailingZeros(amount.toFixed(3));
}

function readStoredSecondaryIncomeThousands(): string {
  if (typeof window === "undefined") return "0";
  return sanitizeThousandsValue(
    window.localStorage.getItem(SECONDARY_INCOME_STORAGE_KEY)
  );
}

function readStoredPrimaryIncomeThousands(): string | null {
  if (typeof window === "undefined") return null;
  const storedValue = window.localStorage.getItem(PRIMARY_INCOME_STORAGE_KEY);
  return storedValue === null
    ? null
    : sanitizeStoredPrimaryIncomeThousands(storedValue);
}

function secondaryIncomeSplitThousands(totalIncome: number): string {
  return dollarsToThousands(roundMoneyNumber(totalIncome * 0.4));
}

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

function stepDollarsFromThousands(value: string): string | null {
  const trimmedValue = value.trim();
  if (trimmedValue === "") return null;
  const amount = Number(trimmedValue);
  if (!Number.isFinite(amount) || amount < 1) return null;
  return trimTrailingZeros((amount * 1000).toFixed(2));
}

function dollarsToThousands(value: string | number): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "0";
  return trimTrailingZeros((amount / 1000).toFixed(3));
}

function nonNegativeDollarsFromThousands(value: string): number | null {
  const trimmedValue = value.trim();
  if (trimmedValue === "") return null;
  const amount = Number(trimmedValue);
  if (!Number.isFinite(amount) || amount < 0) return null;
  return roundMoneyNumber(amount * 1000);
}

function clampStopDollarsAtStart(startDollars: string, stopDollars: string): string {
  const startAmount = Number(startDollars);
  const trimmedStopDollars = stopDollars.trim();
  const stopAmount = Number(trimmedStopDollars);
  const safeStart = Number.isFinite(startAmount) ? Math.max(0, startAmount) : 0;
  if (
    trimmedStopDollars === "" ||
    !Number.isFinite(stopAmount) ||
    stopAmount < safeStart
  ) {
    return String(safeStart);
  }
  return stopDollars;
}

function clampSecondaryDollarsAtStop(
  secondaryDollars: string,
  stopDollars: string
): string {
  const secondaryAmount = Number(secondaryDollars);
  const stopAmount = Number(stopDollars);
  const safeSecondary = Number.isFinite(secondaryAmount)
    ? Math.max(0, secondaryAmount)
    : 0;
  if (!Number.isFinite(stopAmount)) return String(safeSecondary);
  return String(Math.min(safeSecondary, Math.max(0, stopAmount)));
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

function requireFilingStatuses(
  year: number,
  statuses: FilingStatus[]
): FilingStatus[] {
  if (statuses.length === 0) {
    throw new Error(`No filing statuses for ${year}`);
  }
  return statuses;
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
  mode: PretaxDeductionMode,
  dependentCount: number,
  secondaryIncome: number
): number[] {
  const standardDeduction = Number(parameters.federal.standard_deduction);
  const incomes: number[] = [];

  if (mode === "max_available") {
    incomes.push(
      ...maxAvailablePretaxDeductionChangeIncomes(
        parameters,
        dependentCount,
        secondaryIncome
      )
    );
    for (const bracket of parameters.federal.brackets) {
      const income = solveIncomeForTarget(
        standardDeduction + Number(bracket.lower_bound),
        (grossIncome) =>
          incomeAfterPretaxBeforeTax(
            parameters,
            mode,
            dependentCount,
            secondaryIncome,
            grossIncome
          )
      );
      if (income !== null) incomes.push(income);
    }
  } else {
    incomes.push(standardDeduction);
    incomes.push(gradualPhaseInEnd(parameters, dependentCount, secondaryIncome));
    for (const bracket of parameters.federal.brackets.slice(1)) {
      const income = solveIncomeForTarget(
        Number(bracket.lower_bound),
        (grossIncome) =>
          taxableIncomeBeforeTax(
            parameters,
            mode,
            dependentCount,
            secondaryIncome,
            grossIncome
          )
      );
      if (income !== null) incomes.push(income);
    }
  }

  for (let workerIndex = 0; workerIndex < workerCount(parameters, secondaryIncome); workerIndex += 1) {
    const income = solveIncomeForTarget(
      Number(parameters.payroll.social_security_wage_base),
      (grossIncome) =>
        workerPayrollWages(
          parameters,
          mode,
          dependentCount,
          secondaryIncome,
          grossIncome
        )[workerIndex] ?? 0
    );
    if (income !== null) incomes.push(income);
  }

  const additionalMedicareIncome = solveIncomeForTarget(
    additionalMedicareThreshold(parameters),
    (grossIncome) =>
      payrollWages(parameters, mode, dependentCount, secondaryIncome, grossIncome)
  );
  if (additionalMedicareIncome !== null) incomes.push(additionalMedicareIncome);

  return incomes
    .filter((income) => Number.isFinite(income))
    .map(roundMoneyNumber);
}

function maxAvailablePretaxDeductionChangeIncomes(
  parameters: TaxParameters,
  dependentCount: number,
  secondaryIncome: number
): number[] {
  const incomes: number[] = [];
  const caps = pretaxDeductionCaps(parameters, dependentCount, secondaryIncome);
  if (caps.total <= 0) return incomes;

  const standardDeduction = Number(parameters.federal.standard_deduction);
  const probeIncome = Math.max(
    caps.total * 4 + secondaryIncome + standardDeduction,
    1
  );
  const maxDeduction = pretaxDeductionsAtIncome(
    parameters,
    "max_available",
    dependentCount,
    secondaryIncome,
    probeIncome
  ).total;
  const maxDeductionIncome = solveIncomeForTarget(
    maxDeduction,
    (grossIncome) =>
      pretaxDeductionsAtIncome(
        parameters,
        "max_available",
        dependentCount,
        secondaryIncome,
        grossIncome
      ).total
  );
  if (maxDeductionIncome !== null) incomes.push(maxDeductionIncome);

  const workers = workerCount(parameters, secondaryIncome);
  const nonDependentCap = caps.employee401k + caps.healthFsa;
  if (workers > 1 && nonDependentCap > 0) {
    const perWorkerCap = nonDependentCap / workers;
    if (secondaryIncome > perWorkerCap) {
      incomes.push(perWorkerCap);
      incomes.push(secondaryIncome, secondaryIncome + perWorkerCap);
    }
  }

  return incomes;
}

function incomeAfterPretaxBeforeTax(
  parameters: TaxParameters,
  mode: PretaxDeductionMode,
  dependentCount: number,
  secondaryIncome: number,
  grossIncome: number
): number {
  const pretax = pretaxDeductionsAtIncome(
    parameters,
    mode,
    dependentCount,
    secondaryIncome,
    grossIncome
  );
  return Math.max(0, grossIncome - pretax.total);
}

function pretaxDeductionCaps(
  parameters: TaxParameters,
  dependentCount: number,
  secondaryIncome: number
): PretaxDeductionCaps {
  const dualIncome = workerCount(parameters, secondaryIncome) === 2;
  const employee401k =
    Number(parameters.pretax_deductions.employee_401k_limit) *
    (dualIncome ? 2 : 1);
  const healthFsa =
    Number(parameters.pretax_deductions.health_fsa_limit) * (dualIncome ? 2 : 1);
  const configuredDependentCareFsa = Number(
    parameters.pretax_deductions.dependent_care_fsa_limit
  );
  const dependentCareFsa =
    dependentCount > 0
      ? parameters.federal.filing_status === "married_separate"
        ? configuredDependentCareFsa / 2
        : configuredDependentCareFsa
      : 0;

  return {
    employee401k,
    healthFsa,
    dependentCareFsa,
    total: employee401k + healthFsa + dependentCareFsa
  };
}

function totalPretaxDeductionCap(
  parameters: TaxParameters,
  dependentCount: number,
  secondaryIncome: number
): number {
  return pretaxDeductionCaps(parameters, dependentCount, secondaryIncome).total;
}

function gradualPhaseInEnd(
  parameters: TaxParameters,
  dependentCount: number,
  secondaryIncome: number
): number {
  const nextToLastBracket =
    parameters.federal.brackets[
      Math.max(0, parameters.federal.brackets.length - 2)
    ];
  if (workerCount(parameters, secondaryIncome) === 2) {
    const caps = pretaxDeductionCaps(parameters, dependentCount, secondaryIncome);
    const singleWorkerCap =
      caps.employee401k / 2 + caps.healthFsa / 2 + caps.dependentCareFsa;
    return (
      (Number(parameters.federal.standard_deduction) +
        Number(nextToLastBracket?.lower_bound ?? 0) +
        singleWorkerCap) *
      1.5
    );
  }

  return (
    Number(parameters.federal.standard_deduction) +
    Number(nextToLastBracket?.lower_bound ?? 0) +
    totalPretaxDeductionCap(parameters, dependentCount, secondaryIncome)
  );
}

function pretaxDeductionsAtIncome(
  parameters: TaxParameters,
  mode: PretaxDeductionMode,
  dependentCount: number,
  secondaryIncome: number,
  grossIncome: number
) {
  const caps = pretaxDeductionCaps(parameters, dependentCount, secondaryIncome);
  const incomes = workerIncomes(parameters, secondaryIncome, grossIncome);
  if (caps.total <= 0) {
    return {
      total: 0,
      healthFsa: 0,
      dependentCareFsa: 0,
      payrollExclusionsByWorker: incomes.map(() => 0)
    };
  }

  let requestedTotal: number;
  if (mode === "max_available") {
    requestedTotal = Math.min(grossIncome, caps.total);
  } else if (grossIncome <= Number(parameters.federal.standard_deduction)) {
    requestedTotal = 0;
  } else {
    const phaseStart = Number(parameters.federal.standard_deduction);
    const phaseEnd = gradualPhaseInEnd(
      parameters,
      dependentCount,
      secondaryIncome
    );
    const z = Math.max(
      0,
      Math.min(1, (grossIncome - phaseStart) / (phaseEnd - phaseStart))
    );
    const startRate = Number(
      parameters.pretax_deductions.gradual_phase_in_start_rate
    );
    const endRate = caps.total / phaseEnd;
    requestedTotal = Math.min(
      caps.total,
      grossIncome * (startRate + (endRate - startRate) * z)
    );
  }

  const nonDependentCap = caps.employee401k + caps.healthFsa;
  const requestedNonDependent =
    nonDependentCap > 0 ? (requestedTotal * nonDependentCap) / caps.total : 0;
  const workerNonDependent = workerNonDependentPretaxDeductions(
    requestedNonDependent,
    incomes,
    caps
  );
  const healthFsa = workerNonDependent.reduce(
    (total, worker) => total + worker.healthFsa,
    0
  );
  const workerNonDependentTotals = workerNonDependent.map(
    (worker) => worker.total
  );
  const requestedDependentCare =
    caps.dependentCareFsa > 0
      ? (requestedTotal * caps.dependentCareFsa) / caps.total
      : 0;
  const dependentCareByWorker = workerDependentCareDeductions(
    requestedDependentCare,
    incomes,
    workerNonDependentTotals,
    caps
  );
  const dependentCareFsa = dependentCareByWorker.reduce(
    (total, deduction) => total + deduction,
    0
  );
  const payrollExclusionsByWorker = workerNonDependent.map(
    (worker, index) => worker.healthFsa + dependentCareByWorker[index]
  );
  const total =
    workerNonDependentTotals.reduce((sum, deduction) => sum + deduction, 0) +
    dependentCareFsa;

  return {
    total,
    healthFsa,
    dependentCareFsa,
    payrollExclusionsByWorker
  };
}

function workerNonDependentPretaxDeductions(
  requestedDeduction: number,
  workerIncomes: number[],
  caps: PretaxDeductionCaps
): Array<{ total: number; healthFsa: number }> {
  const workers = workerIncomes.length;
  const worker401kCap = caps.employee401k / workers;
  const workerHealthFsaCap = caps.healthFsa / workers;
  const workerTotalCap = worker401kCap + workerHealthFsaCap;
  if (requestedDeduction <= 0 || workerTotalCap <= 0) {
    return workerIncomes.map(() => ({ total: 0, healthFsa: 0 }));
  }

  const capacities = workerIncomes.map((income) =>
    Math.max(0, Math.min(income, workerTotalCap))
  );
  const deduction = Math.min(
    requestedDeduction,
    capacities.reduce((total, capacity) => total + capacity, 0)
  );
  return allocateAmountByWeight(deduction, capacities).map((total) => {
    const healthFsa = total * (workerHealthFsaCap / workerTotalCap);
    return { total, healthFsa };
  });
}

function workerDependentCareDeductions(
  requestedDeduction: number,
  workerIncomes: number[],
  workerNonDependentTotals: number[],
  caps: PretaxDeductionCaps
): number[] {
  if (requestedDeduction <= 0 || caps.dependentCareFsa <= 0) {
    return workerIncomes.map(() => 0);
  }

  const capacities = workerIncomes.map((income, index) =>
    Math.max(0, income - workerNonDependentTotals[index])
  );
  const deduction = Math.min(
    requestedDeduction,
    caps.dependentCareFsa,
    capacities.reduce((total, capacity) => total + capacity, 0)
  );
  return allocateAmountByWeight(deduction, capacities);
}

function taxableIncomeBeforeTax(
  parameters: TaxParameters,
  mode: PretaxDeductionMode,
  dependentCount: number,
  secondaryIncome: number,
  grossIncome: number
): number {
  const pretax = pretaxDeductionsAtIncome(
    parameters,
    mode,
    dependentCount,
    secondaryIncome,
    grossIncome
  );
  return Math.max(
    0,
    grossIncome - pretax.total - Number(parameters.federal.standard_deduction)
  );
}

function payrollWages(
  parameters: TaxParameters,
  mode: PretaxDeductionMode,
  dependentCount: number,
  secondaryIncome: number,
  grossIncome: number
): number {
  return workerPayrollWages(
    parameters,
    mode,
    dependentCount,
    secondaryIncome,
    grossIncome
  ).reduce((total, wages) => total + wages, 0);
}

function workerPayrollWages(
  parameters: TaxParameters,
  mode: PretaxDeductionMode,
  dependentCount: number,
  secondaryIncome: number,
  grossIncome: number
): number[] {
  const pretax = pretaxDeductionsAtIncome(
    parameters,
    mode,
    dependentCount,
    secondaryIncome,
    grossIncome
  );
  const incomes = workerIncomes(parameters, secondaryIncome, grossIncome);
  return incomes.map((income, index) =>
    Math.max(0, income - (pretax.payrollExclusionsByWorker[index] ?? 0))
  );
}

function workerIncomes(
  parameters: TaxParameters,
  secondaryIncome: number,
  grossIncome: number
): number[] {
  if (workerCount(parameters, secondaryIncome) === 1) return [grossIncome];
  const secondary = Math.min(Math.max(0, secondaryIncome), grossIncome);
  return [grossIncome - secondary, secondary];
}

function workerCount(
  parameters: TaxParameters,
  secondaryIncome: number
): number {
  return parameters.federal.filing_status === "married_joint" && secondaryIncome > 0
    ? 2
    : 1;
}

function solveIncomeForTarget(
  target: number,
  valueAtIncome: (grossIncome: number) => number
): number | null {
  if (!Number.isFinite(target) || target < 0 || target >= MAX_MONEY_NUMBER) {
    return null;
  }

  let lower = 0;
  let upper = Math.max(1, target);
  let upperMoney = roundMoneyNumber(upper);
  while (valueAtIncome(upper) < target) {
    if (upper >= MAX_MONEY_NUMBER) return null;
    upper = Math.min(upper * 2, MAX_MONEY_NUMBER);
    upperMoney = roundMoneyNumber(upper);
  }

  let lowerMoney = roundMoneyNumber(lower);
  while (lowerMoney !== upperMoney) {
    const midpoint = lower + (upper - lower) / 2;
    if (midpoint === lower || midpoint === upper) break;
    const midpointMoney = roundMoneyNumber(midpoint);
    if (valueAtIncome(midpoint) < target) {
      lower = midpoint;
      lowerMoney = midpointMoney;
    } else {
      upper = midpoint;
      upperMoney = midpointMoney;
    }
  }

  return upperMoney < MAX_MONEY_NUMBER ? upperMoney : null;
}

function roundMoneyNumber(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function allocateAmountByWeight(amount: number, weights: number[]): number[] {
  const totalWeight = weights.reduce((total, weight) => total + weight, 0);
  if (amount <= 0 || totalWeight <= 0) return weights.map(() => 0);

  let remainingAmount = amount;
  return weights.map((weight, index) => {
    if (index === weights.length - 1) return remainingAmount;
    const allocation = (amount * weight) / totalWeight;
    remainingAmount -= allocation;
    return allocation;
  });
}

function sortedUniqueNumbers(values: Iterable<number>): number[] {
  return [...new Set(values)].sort((left, right) => left - right);
}

function defaultStopThousands(
  parameters: TaxParameters,
  mode: PretaxDeductionMode,
  dependentCount: number,
  secondaryIncome: number
): string {
  const lastChangeIncome = Math.max(
    ...marginalRateChangeIncomes(
      parameters,
      mode,
      dependentCount,
      secondaryIncome
    )
  );
  return dollarsToThousands(
    Math.min(lastChangeIncome * 1.1, MAX_AUTOMATIC_STOP)
  );
}

function defaultSeriesStep(
  start: number,
  stop: number,
  requestedStep: number,
  parameters: TaxParameters,
  mode: PretaxDeductionMode,
  dependentCount: number,
  secondaryIncome: number
): number {
  const breakpointCount = marginalRateChangeIncomes(
    parameters,
    mode,
    dependentCount,
    secondaryIncome
  ).filter((income) => income >= start && income <= stop).length;
  const gridRowBudget = Math.max(
    2,
    MAX_INCOME_SERIES_ROWS - breakpointCount - 1
  );
  const minimumStep =
    stop <= start
      ? requestedStep
      : Math.ceil(((stop - start) / (gridRowBudget - 1)) * 100) / 100;
  return Math.max(requestedStep, minimumStep);
}

function buildChartRows(
  rows: TaxBurden[],
  includeEmployer: boolean,
  marginalBreakpointIncomes: readonly string[] = [],
  legacyMarginalBreakpointIncomes: readonly number[] = []
): ChartRow[] {
  const breakpointIncomes = new Set(marginalBreakpointIncomes);
  const legacyBreakpointIncomes = new Set(legacyMarginalBreakpointIncomes);
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
      isMarginalBreakpoint:
        breakpointIncomes.has(row.gross_income) ||
        legacyBreakpointIncomes.has(incomeNumber),
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

function formatCapUsage(
  amount: string | number,
  cap: string | number,
  inactiveLabel = "Inactive ($0 cap)"
): string {
  const capNumber = Number(cap);
  if (capNumber <= 0) return inactiveLabel;
  const amountNumber = Number(amount);
  const usage = Math.max(0, Math.min(100, (amountNumber / capNumber) * 100));
  return `${formatPercentValue(usage)} of ${toCurrency(capNumber)} max`;
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

function ChartTooltip({
  active,
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
              <span>Total tax {toCurrency(totalTax ?? 0)}</span>
              <span>Effective rate {formatPercentValue(totalRate ?? 0)}</span>
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
  const [loadedFilingStatusesYear, setLoadedFilingStatusesYear] = useState<
    number | null
  >(null);
  const [failedFilingStatusesYear, setFailedFilingStatusesYear] = useState<
    number | null
  >(null);
  const [year, setYear] = useState(DEFAULT_TAX_YEAR);
  const [filingStatus, setFilingStatus] = useState("single");
  const [startThousands, setStartThousands] = useState("0");
  const [stopThousands, setStopThousands] = useState("");
  const [hasCustomStop, setHasCustomStop] = useState(false);
  const [stepThousands, setStepThousands] = useState(DEFAULT_STEP_THOUSANDS);
  const [hasCustomStep, setHasCustomStep] = useState(false);
  const [selectedIncome, setSelectedIncome] = useState(100000);
  const [hasCustomSelectedIncome, setHasCustomSelectedIncome] = useState(false);
  const hasCustomSelectedIncomeRef = useRef(false);
  const stopEditCollapseAnchorRef = useRef<{
    selectedIncome: number;
    start: number;
  } | null>(null);
  const [includeEmployer, setIncludeEmployer] = useState(false);
  const [pretaxDeductionMode, setPretaxDeductionMode] =
    useState<PretaxDeductionMode>("gradual_phase_in");
  const [dependentCountInput, setDependentCountInput] = useState(
    readStoredDependentCount
  );
  const filingStatusCacheByYearRef = useRef<Record<number, FilingStatus[]>>({});
  const [storedPrimaryIncomeThousands, setStoredPrimaryIncomeThousands] =
    useState(readStoredPrimaryIncomeThousands);
  const [secondaryIncomeThousands, setSecondaryIncomeThousands] = useState(
    readStoredSecondaryIncomeThousands
  );
  const [hasCustomIncomeSplit, setHasCustomIncomeSplit] = useState(false);
  const hasCustomIncomeSplitRef = useRef(false);
  const hasAppliedStoredIncomeSplitRef = useRef(false);
  const [compareFilingStatuses, setCompareFilingStatuses] = useState(false);
  const [compareTaxYears, setCompareTaxYears] = useState(false);
  const [chartMode, setChartMode] = useState<ChartMode>("effectiveRate");
  const [parameters, setParameters] = useState<TaxParameters | null>(null);
  const [rows, setRows] = useState<TaxBurden[]>([]);
  const [marginalBreakpointIncomes, setMarginalBreakpointIncomes] = useState<
    string[]
  >([]);
  const [hasMarginalBreakpointMetadata, setHasMarginalBreakpointMetadata] =
    useState(true);
  const [selectedBurden, setSelectedBurden] = useState<TaxBurden | null>(null);
  const [comparisonSeries, setComparisonSeries] = useState<CurveSeries[]>([]);
  const [loading, setLoading] = useState(true);
  const [taxYearDiscoveryError, setTaxYearDiscoveryError] = useState<
    string | null
  >(null);
  const [scenarioError, setScenarioError] = useState<string | null>(null);
  const [selectedIncomeError, setSelectedIncomeError] = useState<string | null>(
    null
  );
  const selectedScenarioFailedRef = useRef(false);
  const start = thousandsToDollars(startThousands);
  const stop = thousandsToDollars(stopThousands);
  const effectiveStop = clampStopDollarsAtStart(start, stop);
  const step = stepDollarsFromThousands(stepThousands);
  const dependentCount = sanitizeDependentCount(dependentCountInput);
  const rawSecondaryIncome = Number(
    thousandsToDollars(secondaryIncomeThousands)
  );
  const secondaryIncome =
    filingStatus === "married_joint" ? Math.max(0, rawSecondaryIncome) : 0;
  const configuredPrimaryIncome = Number(
    thousandsToDollars(storedPrimaryIncomeThousands ?? "0")
  );
  const configuredIncomeSplitTotal =
    filingStatus === "married_joint"
      ? Math.max(0, configuredPrimaryIncome) + secondaryIncome
      : 0;
  const selectedIncomeMax = Math.max(
    SELECTED_INCOME_MAX_FLOOR,
    Math.min(
      Number(effectiveStop) || 0,
      SELECTED_INCOME_LINEAR_RANGE_LIMIT
    ),
    Number(start) || 0,
    configuredIncomeSplitTotal,
    selectedIncome
  );
  const primaryIncome = Math.max(0, selectedIncome - secondaryIncome);
  const activeSecondaryIncome = Math.min(secondaryIncome, selectedIncome);
  const secondaryIncomeRequest = String(activeSecondaryIncome);
  const selectedFilingStatus = filingStatuses.find(
    (status) => status.code === filingStatus
  );
  const isSelectedStatusReady =
    loadedFilingStatusesYear === year &&
    filingStatuses.some((status) => status.code === filingStatus);
  const filingStatusLoadFailedForYear = failedFilingStatusesYear === year;
  const displayedErrors = [
    taxYearDiscoveryError,
    scenarioError ?? selectedIncomeError
  ].filter((error): error is string => Boolean(error));

  useEffect(() => {
    window.localStorage.setItem(
      DEPENDENT_COUNT_STORAGE_KEY,
      String(dependentCount)
    );
  }, [dependentCount]);

  useEffect(() => {
    window.localStorage.setItem(
      SECONDARY_INCOME_STORAGE_KEY,
      sanitizeThousandsValue(secondaryIncomeThousands)
    );
  }, [secondaryIncomeThousands]);

  useEffect(() => {
    if (storedPrimaryIncomeThousands === null) return;
    window.localStorage.setItem(
      PRIMARY_INCOME_STORAGE_KEY,
      sanitizeThousandsValue(storedPrimaryIncomeThousands)
    );
  }, [storedPrimaryIncomeThousands]);

  useEffect(() => {
    fetchTaxYears()
      .then((years) => {
        const nextYears =
          years.length > 0 ? years : [DEFAULT_TAX_YEAR];
        setTaxYears(nextYears);
        setTaxYearDiscoveryError(null);
        setYear(Math.max(...nextYears));
      })
      .catch((nextError: Error) => {
        setTaxYears([DEFAULT_TAX_YEAR]);
        setTaxYearDiscoveryError(nextError.message);
      });
  }, []);

  useEffect(() => {
    let cancelled = false;
    setFailedFilingStatusesYear(null);
    fetchFilingStatuses(year)
      .then((statuses) => {
        if (cancelled) return;
        const nextStatuses = requireFilingStatuses(year, statuses);
        filingStatusCacheByYearRef.current[year] = nextStatuses;
        setFailedFilingStatusesYear(null);
        setFilingStatuses(nextStatuses);
        setLoadedFilingStatusesYear(year);
        setFilingStatus((currentStatus) =>
          nextStatuses.some((status) => status.code === currentStatus)
            ? currentStatus
            : nextStatuses[0].code
        );
      })
      .catch((nextError: Error) => {
        if (!cancelled) {
          selectedScenarioFailedRef.current = true;
          setFailedFilingStatusesYear(year);
          setScenarioError(nextError.message);
          delete filingStatusCacheByYearRef.current[year];
          setFilingStatuses([]);
          setLoadedFilingStatusesYear(null);
          setParameters(null);
          setRows([]);
          setMarginalBreakpointIncomes([]);
          setHasMarginalBreakpointMetadata(true);
          setSelectedBurden(null);
          setComparisonSeries([]);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [year]);

  useEffect(() => {
    let cancelled = false;

    if (!isSelectedStatusReady) {
      if (!filingStatusLoadFailedForYear) {
        setLoading(true);
        setScenarioError(null);
      }
      return () => {
        cancelled = true;
      };
    }
    if (step === null) {
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    const validStep = step;

    setLoading(true);
    setScenarioError(null);
    selectedScenarioFailedRef.current = false;

    async function loadScenario() {
      const nextParameters = await fetchTaxParameters(year, filingStatus);
      const nextDefaultStopThousands = defaultStopThousands(
        nextParameters,
        pretaxDeductionMode,
        dependentCount,
        secondaryIncome
      );
      const requestedStop = hasCustomStop
        ? effectiveStop
        : thousandsToDollars(nextDefaultStopThousands);
      const resolvedStop = clampStopDollarsAtStart(start, requestedStop);
      const resolvedStep = hasCustomStep
        ? Number(validStep)
        : defaultSeriesStep(
            Number(start),
            Number(resolvedStop),
            DEFAULT_STEP_DOLLARS,
            nextParameters,
            pretaxDeductionMode,
            dependentCount,
            secondaryIncome
          );
      const resolvedSecondaryIncomeRequest = clampSecondaryDollarsAtStop(
        secondaryIncomeRequest,
        resolvedStop
      );
      const selectedSeriesRequest = {
        year,
        filingStatus,
        start,
        stop: resolvedStop,
        step: String(resolvedStep),
        includeEmployerPayrollTax: includeEmployer,
        includeMarginalBreakpoints: true,
        dependentCount,
        secondaryIncome: resolvedSecondaryIncomeRequest,
        pretaxDeductionMode
      };
      const selectedSeries = await fetchIncomeSeries(selectedSeriesRequest);
      const selectedCurveSeries = {
        key: seriesKey(year, filingStatus),
        label: comparisonSeriesLabel(
          year,
          selectedFilingStatus?.label ?? filingStatus,
          compareFilingStatuses,
          compareTaxYears
        ),
        color: seriesColor(0),
        rows: buildChartRows(
          selectedSeries.rows,
          includeEmployer,
          selectedSeries.marginal_breakpoint_incomes
        )
      };

      if (cancelled) return;
      if (!hasCustomStop && stopThousands !== nextDefaultStopThousands) {
        setStopThousands(nextDefaultStopThousands);
      }
      const nextDefaultStepThousands = dollarsToThousands(resolvedStep);
      if (!hasCustomStep && stepThousands !== nextDefaultStepThousands) {
        setStepThousands(nextDefaultStepThousands);
      }
      selectedScenarioFailedRef.current = false;
      setParameters(nextParameters);
      setRows(selectedSeries.rows);
      setMarginalBreakpointIncomes(
        selectedSeries.marginal_breakpoint_incomes
      );
      setHasMarginalBreakpointMetadata(
        selectedSeries.has_marginal_breakpoint_metadata
      );
      setComparisonSeries([selectedCurveSeries]);

      let nextComparisonSeries: CurveSeries[];
      try {
        const yearsToCompare =
          compareTaxYears && taxYears.length > 0 ? taxYears : [year];
        const seriesRequests: Array<{
          year: number;
          filingStatus: string;
          statusLabel: string;
        }> = [];

        for (const comparisonYear of yearsToCompare) {
          let statuses = filingStatusCacheByYearRef.current[comparisonYear];
          if (
            !statuses &&
            comparisonYear === year &&
            filingStatuses.length > 0
          ) {
            statuses = filingStatuses;
            filingStatusCacheByYearRef.current[comparisonYear] = statuses;
          }
          if (!statuses) {
            statuses = await fetchFilingStatuses(comparisonYear);
            if (cancelled) return;
          }
          statuses = requireFilingStatuses(comparisonYear, statuses);
          filingStatusCacheByYearRef.current[comparisonYear] = statuses;
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

        nextComparisonSeries = await Promise.all(
          seriesRequests.map(async (request, index) => {
            const isSelectedSeries =
              request.year === year && request.filingStatus === filingStatus;
            const response = isSelectedSeries
              ? selectedSeries
              : await fetchIncomeSeries({
                  ...selectedSeriesRequest,
                  year: request.year,
                  filingStatus: request.filingStatus,
                  secondaryIncome:
                    request.filingStatus === "married_joint"
                      ? selectedSeriesRequest.secondaryIncome
                      : "0"
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
              rows: buildChartRows(
                response.rows,
                includeEmployer,
                response.marginal_breakpoint_incomes
              )
            };
          })
        );
      } catch (nextError) {
        if (!cancelled) setScenarioError((nextError as Error).message);
        return;
      }

      if (cancelled) return;
      setComparisonSeries(nextComparisonSeries);
    }

    loadScenario()
      .catch((nextError: Error) => {
        if (cancelled) return;
        selectedScenarioFailedRef.current = true;
        setParameters(null);
        setRows([]);
        setMarginalBreakpointIncomes([]);
        setHasMarginalBreakpointMetadata(true);
        setSelectedBurden(null);
        setComparisonSeries([]);
        setScenarioError(nextError.message);
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
    effectiveStop,
    step,
    stopThousands,
    hasCustomStop,
    hasCustomStep,
    includeEmployer,
    pretaxDeductionMode,
    dependentCount,
    secondaryIncome,
    secondaryIncomeRequest,
    compareFilingStatuses,
    compareTaxYears,
    taxYears,
    filingStatuses,
    isSelectedStatusReady,
    filingStatusLoadFailedForYear
  ]);

  useEffect(() => {
    let cancelled = false;

    if (!isSelectedStatusReady) {
      return () => {
        cancelled = true;
      };
    }

    fetchTaxBurden({
      year,
      filingStatus,
      grossIncome: String(selectedIncome),
      includeEmployerPayrollTax: includeEmployer,
      dependentCount,
      secondaryIncome: secondaryIncomeRequest,
      pretaxDeductionMode
    })
      .then((burden) => {
        if (!cancelled && !selectedScenarioFailedRef.current) {
          setSelectedBurden(burden);
          setSelectedIncomeError(null);
        }
      })
      .catch((nextError: Error) => {
        if (cancelled || selectedScenarioFailedRef.current) return;
        setSelectedBurden(null);
        setSelectedIncomeError(nextError.message);
      });

    return () => {
      cancelled = true;
    };
  }, [
    year,
    filingStatus,
    selectedIncome,
    includeEmployer,
    pretaxDeductionMode,
    dependentCount,
    secondaryIncomeRequest,
    isSelectedStatusReady
  ]);

  const chartRows = useMemo<ChartRow[]>(() => {
    const legacyBreakpointIncomes =
      !hasMarginalBreakpointMetadata && parameters
        ? marginalRateChangeIncomes(
            parameters,
            pretaxDeductionMode,
            dependentCount,
            secondaryIncome
          ).filter(
            (income) => income >= Number(start) && income <= Number(effectiveStop)
          )
        : [];
    return buildChartRows(
      rows,
      includeEmployer,
      marginalBreakpointIncomes,
      legacyBreakpointIncomes
    );
  }, [
    dependentCount,
    effectiveStop,
    hasMarginalBreakpointMetadata,
    includeEmployer,
    marginalBreakpointIncomes,
    parameters,
    pretaxDeductionMode,
    rows,
    secondaryIncome,
    start
  ]);

  const selectedRow = useMemo(() => {
    if (selectedBurden) return buildChartRows([selectedBurden], includeEmployer)[0];
    return nearestRow(chartRows, selectedIncome);
  }, [chartRows, includeEmployer, selectedBurden, selectedIncome]);
  const selectedDeductionUsage = useMemo(() => {
    if (!selectedRow || !parameters) return [];
    const caps = pretaxDeductionCaps(
      parameters,
      dependentCount,
      secondaryIncome
    );
    const configuredDependentCareFsa = Number(
      parameters.pretax_deductions.dependent_care_fsa_limit
    );
    return [
      {
        label: "Total pre-tax",
        amount: selectedRow.total_pretax_deductions,
        cap: caps.total
      },
      {
        label: "401(k) contribution",
        amount: selectedRow.employee_401k_contribution,
        cap: caps.employee401k
      },
      {
        label: "Health FSA contribution",
        amount: selectedRow.health_fsa_contribution,
        cap: caps.healthFsa
      },
      {
        label: "Dependent-care FSA",
        amount: selectedRow.dependent_care_fsa_contribution,
        cap: caps.dependentCareFsa,
        inactiveLabel: `No dependents (${toCurrency(
          configuredDependentCareFsa
        )} max)`
      }
    ] satisfies DeductionUsageItem[];
  }, [dependentCount, parameters, secondaryIncome, selectedRow]);

  const tableRows = useMemo(() => {
    const startAmount = Number(start) || 0;
    return chartRows.filter(
      (row) => row.incomeNumber === startAmount || row.isMarginalBreakpoint
    );
  }, [chartRows, start]);

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
  const defaultSelectedIncome =
    sampledIncomeOptions.length > 0
      ? (sampledIncomeOptions.filter((income) => income > 0).pop() ??
        sampledIncomeOptions[sampledIncomeOptions.length - 1])
      : undefined;

  useEffect(() => {
    if (
      filingStatus !== "married_joint" ||
      storedPrimaryIncomeThousands === null ||
      hasAppliedStoredIncomeSplitRef.current
    ) {
      return;
    }

    const storedPrimaryIncome =
      Number(thousandsToDollars(storedPrimaryIncomeThousands)) || 0;
    const storedSecondaryIncome =
      Number(thousandsToDollars(secondaryIncomeThousands)) || 0;
    hasAppliedStoredIncomeSplitRef.current = true;
    hasCustomSelectedIncomeRef.current = true;
    hasCustomIncomeSplitRef.current = true;
    setHasCustomSelectedIncome(true);
    setHasCustomIncomeSplit(true);
    setSelectedIncome(
      Math.max(0, storedPrimaryIncome) + Math.max(0, storedSecondaryIncome)
    );
  }, [filingStatus, secondaryIncomeThousands, storedPrimaryIncomeThousands]);

  useEffect(() => {
    if (
      loading ||
      hasCustomSelectedIncomeRef.current ||
      defaultSelectedIncome === undefined
    ) {
      return;
    }
    setSelectedIncome((currentIncome) =>
      currentIncome === defaultSelectedIncome
        ? currentIncome
        : defaultSelectedIncome
    );
  }, [defaultSelectedIncome, hasCustomSelectedIncome, loading]);

  useEffect(() => {
    if (
      filingStatus !== "married_joint" ||
      hasCustomIncomeSplitRef.current ||
      hasCustomSelectedIncomeRef.current ||
      selectedIncome <= 0
    ) {
      return;
    }

    const nextSecondaryIncomeThousands =
      secondaryIncomeSplitThousands(selectedIncome);
    setSecondaryIncomeThousands((currentValue) =>
      currentValue === nextSecondaryIncomeThousands
        ? currentValue
        : nextSecondaryIncomeThousands
    );
  }, [
    filingStatus,
    hasCustomIncomeSplit,
    hasCustomSelectedIncome,
    selectedIncome
  ]);

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
  const payrollBreakdownRows =
    includeEmployer && selectedRow ? (selectedRow.payroll_breakdown ?? []) : [];
  const totalPayrollBreakdownRow = payrollBreakdownRows.find(
    (row) => row.label === "Total"
  );
  const combinedPayrollTax =
    totalPayrollBreakdownRow?.total_payroll_tax ??
    String(
      Number(selectedRow?.total_employee_payroll_tax ?? 0) +
        Number(selectedRow?.total_employer_payroll_tax ?? 0)
    );
  const markCustomSelectedIncome = () => {
    hasCustomSelectedIncomeRef.current = true;
    setHasCustomSelectedIncome(true);
  };
  const markCustomIncomeSplit = () => {
    hasCustomIncomeSplitRef.current = true;
    setHasCustomIncomeSplit(true);
  };
  const handleChartClick = (state: unknown) => {
    const income = readClickedIncome(state);
    if (income !== null) {
      stopEditCollapseAnchorRef.current = null;
      markCustomSelectedIncome();
      setSelectedIncome(income);
    }
  };
  const setQuickStart = (income: number) => {
    stopEditCollapseAnchorRef.current = null;
    setStartThousands(dollarsToThousands(income));
    markCustomSelectedIncome();
    setSelectedIncome((currentIncome) => Math.max(currentIncome, income));
  };
  const setQuickStop = (income: number) => {
    stopEditCollapseAnchorRef.current = null;
    setHasCustomStop(true);
    setStopThousands(dollarsToThousands(income));
    markCustomSelectedIncome();
    setSelectedIncome((currentIncome) => Math.min(currentIncome, income));
  };
  const setManualStartThousands = (value: string) => {
    stopEditCollapseAnchorRef.current = null;
    setStartThousands(value);
    markCustomSelectedIncome();
    const nextStart = nonNegativeDollarsFromThousands(value);
    if (nextStart === null) return;
    const currentStop = nonNegativeDollarsFromThousands(stopThousands);
    if (currentStop !== null && nextStart > currentStop) {
      setHasCustomStop(true);
      setStopThousands(dollarsToThousands(nextStart));
      setSelectedIncome(nextStart);
      return;
    }
    setSelectedIncome((currentIncome) => Math.max(currentIncome, nextStart));
  };
  const setManualStopThousands = (value: string) => {
    setHasCustomStop(true);
    setStopThousands(value);
    markCustomSelectedIncome();
    const nextStop = nonNegativeDollarsFromThousands(value);
    if (nextStop === null) return;
    const currentStart = nonNegativeDollarsFromThousands(startThousands);
    const stopEditAnchor = stopEditCollapseAnchorRef.current;
    const comparisonStart = stopEditAnchor?.start ?? currentStart;
    if (comparisonStart !== null && nextStop < comparisonStart) {
      if (stopEditAnchor === null) {
        stopEditCollapseAnchorRef.current = {
          selectedIncome,
          start: comparisonStart
        };
      }
      setStartThousands(dollarsToThousands(nextStop));
      setSelectedIncome(nextStop);
      return;
    }
    if (stopEditAnchor !== null) {
      setStartThousands(dollarsToThousands(stopEditAnchor.start));
      setSelectedIncome(
        Math.min(
          Math.max(stopEditAnchor.selectedIncome, stopEditAnchor.start),
          nextStop
        )
      );
      stopEditCollapseAnchorRef.current = null;
      return;
    }
    setSelectedIncome((currentIncome) => Math.min(currentIncome, nextStop));
  };
  const setPrimaryIncomeThousands = (value: string) => {
    const nextPrimaryIncome = Math.max(0, Number(thousandsToDollars(value)) || 0);
    stopEditCollapseAnchorRef.current = null;
    markCustomSelectedIncome();
    markCustomIncomeSplit();
    setStoredPrimaryIncomeThousands(value);
    setSelectedIncome(nextPrimaryIncome + activeSecondaryIncome);
  };
  const setSecondaryIncomeThousandsValue = (value: string) => {
    const nextSecondaryIncome = Math.max(0, Number(thousandsToDollars(value)) || 0);
    stopEditCollapseAnchorRef.current = null;
    markCustomSelectedIncome();
    markCustomIncomeSplit();
    setStoredPrimaryIncomeThousands(dollarsToThousands(primaryIncome));
    setSecondaryIncomeThousands(value);
    setSelectedIncome(primaryIncome + nextSecondaryIncome);
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

          <label className="tax-year-field">
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

          <label className="dependent-count-field" htmlFor="dependent-count">
            <span>Dependents</span>
            <input
              id="dependent-count"
              type="number"
              min="0"
              step="1"
              inputMode="numeric"
              value={dependentCountInput}
              onChange={(event) => setDependentCountInput(event.target.value)}
              onBlur={() => setDependentCountInput(String(dependentCount))}
            />
          </label>

          {filingStatus === "married_joint" ? (
            <div className="field-grid">
              <label htmlFor="primary-income-thousands">
                <span>Income 1 ($k)</span>
                <input
                  id="primary-income-thousands"
                  type="number"
                  min="0"
                  step="0.001"
                  value={dollarsToThousands(primaryIncome)}
                  onChange={(event) =>
                    setPrimaryIncomeThousands(event.target.value)
                  }
                />
              </label>
              <label htmlFor="secondary-income-thousands">
                <span>Income 2 ($k)</span>
                <input
                  id="secondary-income-thousands"
                  type="number"
                  min="0"
                  step="0.001"
                  value={secondaryIncomeThousands}
                  onChange={(event) =>
                    setSecondaryIncomeThousandsValue(event.target.value)
                  }
                  onBlur={() =>
                    setSecondaryIncomeThousands(
                      sanitizeThousandsValue(secondaryIncomeThousands)
                    )
                  }
                />
              </label>
            </div>
          ) : null}

          <div className="range-card" aria-label="Income range">
            <div className="range-input-grid">
              <label htmlFor="start-thousands">
                <span>Start ($k)</span>
                <input
                  id="start-thousands"
                  type="number"
                  min="0"
                  step="0.001"
                  value={startThousands}
                  onChange={(event) =>
                    setManualStartThousands(event.target.value)
                  }
                />
              </label>
              <label htmlFor="stop-thousands">
                <span>Stop ($k)</span>
                <input
                  id="stop-thousands"
                  type="number"
                  min="0"
                  step="0.001"
                  value={stopThousands}
                  onChange={(event) =>
                    setManualStopThousands(event.target.value)
                  }
                  onBlur={() => {
                    stopEditCollapseAnchorRef.current = null;
                  }}
                />
              </label>
            </div>
            <details className="range-preset-group">
              <summary>
                <span>Start presets</span>
                <span>{formatThousandsOption(Number(start) || 0)}</span>
              </summary>
              <div className="range-chip-list" aria-label="Start presets">
                {quickStartOptions.map((income) => (
                  <button
                    key={income}
                    type="button"
                    aria-label={`Start ${formatThousandsOption(income)}`}
                    aria-pressed={Number(start) === income}
                    className={Number(start) === income ? "active" : ""}
                    onClick={() => setQuickStart(income)}
                  >
                    {formatThousandsOption(income)}
                  </button>
                ))}
              </div>
            </details>
            <details className="range-preset-group">
              <summary>
                <span>Stop presets</span>
                <span>{formatThousandsOption(Number(effectiveStop) || 0)}</span>
              </summary>
              <div className="range-chip-list" aria-label="Stop presets">
                {quickStopOptions.map((income) => (
                  <button
                    key={income}
                    type="button"
                    aria-label={`Stop ${formatThousandsOption(income)}`}
                    aria-pressed={Number(effectiveStop) === income}
                    className={Number(effectiveStop) === income ? "active" : ""}
                    onClick={() => setQuickStop(income)}
                  >
                    {formatThousandsOption(income)}
                  </button>
                ))}
              </div>
            </details>
          </div>

          <label className="step-size-field">
            <span>Step ($k)</span>
            <input
              type="number"
              min="1"
              value={stepThousands}
              onChange={(event) => {
                setStepThousands(event.target.value);
                setHasCustomStep(true);
              }}
              onBlur={() => {
                if (stepDollarsFromThousands(stepThousands) === null) {
                  setStepThousands("1");
                }
              }}
            />
          </label>

          <label>
            <span>Selected income</span>
            <input
              type="range"
              min={Number(start) || 0}
              max={selectedIncomeMax}
              step={1}
              value={selectedIncome}
              onChange={(event) => {
                stopEditCollapseAnchorRef.current = null;
                markCustomSelectedIncome();
                setSelectedIncome(Number(event.target.value));
              }}
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
            onClick={() => {
              stopEditCollapseAnchorRef.current = null;
              markCustomSelectedIncome();
              setSelectedIncome(Number(start) || 0);
            }}
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

          {displayedErrors.map((displayedError, index) => (
            <div className="error-box" key={`${displayedError}-${index}`}>
              {displayedError}
            </div>
          ))}

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
                  domain={[Number(start) || 0, Number(effectiveStop) || "dataMax"]}
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

          {includeEmployer && selectedRow ? (
            <section
              className="employer-payroll-section"
              aria-label="Employer payroll tax details"
            >
              <div className="employer-payroll-heading">
                <div>
                  <h3>Employer Payroll Breakdown</h3>
                  <p>
                    Selected income {toCurrency(selectedRow.gross_income)}
                  </p>
                </div>
                <strong>
                  Employer-paid{" "}
                  {toCurrency(selectedRow.total_employer_payroll_tax)}
                </strong>
              </div>

              <div className="payroll-overview">
                <Metric
                  label="Employer-paid payroll tax"
                  value={toCurrency(selectedRow.total_employer_payroll_tax)}
                />
                <Metric
                  label="Employee payroll tax"
                  value={toCurrency(selectedRow.total_employee_payroll_tax)}
                />
                <Metric
                  label="Combined payroll tax"
                  value={toCurrency(combinedPayrollTax)}
                />
              </div>

              {payrollBreakdownRows.length > 0 ? (
                <div className="payroll-table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Earner</th>
                        <th>Gross income</th>
                        <th>Payroll wages</th>
                        <th>Employee SS</th>
                        <th>Employee Medicare</th>
                        <th>Addl Medicare</th>
                        <th>Employer SS</th>
                        <th>Employer Medicare</th>
                        <th>Employer total</th>
                        <th>Combined payroll</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payrollBreakdownRows.map((row) => (
                        <tr
                          key={row.label}
                          className={row.label === "Total" ? "total-row" : ""}
                        >
                          <td>{row.label}</td>
                          <td>{toCurrency(row.gross_income)}</td>
                          <td>{toCurrency(row.payroll_wages)}</td>
                          <td>{toCurrency(row.employee_social_security_tax)}</td>
                          <td>{toCurrency(row.employee_medicare_tax)}</td>
                          <td>
                            {toCurrency(row.employee_additional_medicare_tax)}
                          </td>
                          <td>{toCurrency(row.employer_social_security_tax)}</td>
                          <td>{toCurrency(row.employer_medicare_tax)}</td>
                          <td>{toCurrency(row.total_employer_payroll_tax)}</td>
                          <td>{toCurrency(row.total_payroll_tax)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </section>
          ) : null}

          <section
            className="deduction-usage"
            aria-label="Deduction usage details"
          >
            <div className="deduction-usage-heading">
              <h3>Deduction Usage</h3>
              <span>
                Selected income{" "}
                {selectedRow ? toCurrency(selectedRow.gross_income) : "-"}
              </span>
            </div>
            <dl>
              {selectedDeductionUsage.map((item) => (
                <div key={item.label}>
                  <dt>{item.label}</dt>
                  <dd>
                    <strong>{toCurrency(item.amount)}</strong>
                    <span>
                      {formatCapUsage(
                        item.amount,
                        item.cap,
                        item.inactiveLabel
                      )}
                    </span>
                  </dd>
                </div>
              ))}
            </dl>
          </section>

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
          <div className="sampled-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Income</th>
                  <th>Pre-tax deductions</th>
                  <th>401(k)</th>
                  <th>Health FSA</th>
                  <th>Dependent care</th>
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
                    <td>{toCurrency(row.dependent_care_fsa_contribution)}</td>
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
          </div>
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
