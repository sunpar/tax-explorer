import type {
  FilingStatus,
  IncomeSeriesResponse,
  TaxBurden,
  TaxParameters
} from "./types";

export type SeriesRequest = {
  year: number;
  filingStatus: string;
  start: string;
  stop: string;
  step: string;
  includeEmployerPayrollTax: boolean;
  includeMarginalBreakpoints?: boolean;
  dependentCount: number;
  secondaryIncome: string;
  pretaxDeductionMode: "max_available" | "gradual_phase_in";
};

export type CalculateRequest = {
  year: number;
  filingStatus: string;
  grossIncome: string;
  includeEmployerPayrollTax: boolean;
  dependentCount: number;
  secondaryIncome: string;
  pretaxDeductionMode: "max_available" | "gradual_phase_in";
};

async function requestJson<T>(
  url: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchTaxYears(): Promise<number[]> {
  const response = await requestJson<{ years: number[] }>("/api/tax-years");
  return response.years;
}

export async function fetchFilingStatuses(year: number): Promise<FilingStatus[]> {
  const response = await requestJson<{ statuses: FilingStatus[] }>(
    `/api/tax-years/${year}/filing-statuses`
  );
  return response.statuses;
}

export function fetchTaxParameters(
  year: number,
  filingStatus: string
): Promise<TaxParameters> {
  const params = new URLSearchParams({ filing_status: filingStatus });
  return requestJson<TaxParameters>(
    `/api/tax-years/${year}/parameters?${params.toString()}`
  );
}

export function fetchIncomeSeries(
  request: SeriesRequest
): Promise<IncomeSeriesResponse> {
  const params = new URLSearchParams({
    year: String(request.year),
    filing_status: request.filingStatus,
    start: request.start,
    stop: request.stop,
    step: request.step,
    include_employer_payroll_tax: String(
      request.includeEmployerPayrollTax
    ),
    include_marginal_breakpoints: String(
      request.includeMarginalBreakpoints ?? false
    ),
    dependent_count: String(request.dependentCount),
    secondary_income: request.secondaryIncome,
    pretax_deduction_mode: request.pretaxDeductionMode
  });
  return requestJson<IncomeSeriesResponse>(
    `/api/income-series?${params.toString()}`
  );
}

export function fetchTaxBurden(request: CalculateRequest): Promise<TaxBurden> {
  return requestJson<TaxBurden>("/api/calculate", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      year: request.year,
      filing_status: request.filingStatus,
      gross_income: request.grossIncome,
      include_employer_payroll_tax: request.includeEmployerPayrollTax,
      dependent_count: request.dependentCount,
      secondary_income: request.secondaryIncome,
      pretax_deduction_mode: request.pretaxDeductionMode
    })
  });
}
