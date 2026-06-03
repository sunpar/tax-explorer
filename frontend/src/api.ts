import type { FilingStatus, IncomeSeriesResponse, TaxParameters } from "./types";

export type SeriesRequest = {
  year: number;
  filingStatus: string;
  start: string;
  stop: string;
  step: string;
  includeEmployerPayrollTax: boolean;
};

async function requestJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
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
    )
  });
  return requestJson<IncomeSeriesResponse>(
    `/api/income-series?${params.toString()}`
  );
}
