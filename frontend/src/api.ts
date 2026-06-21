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
    throw new Error(errorMessageFromResponse(message, response.status));
  }
  return response.json() as Promise<T>;
}

function errorMessageFromResponse(message: string, status: number): string {
  if (!message) return `Request failed with ${status}`;
  if (!startsWithJsonObject(message)) return message;

  try {
    const body = JSON.parse(message) as unknown;
    if (
      body &&
      typeof body === "object" &&
      "detail" in body &&
      typeof body.detail === "string"
    ) {
      return body.detail;
    }
    if (
      body &&
      typeof body === "object" &&
      "detail" in body &&
      Array.isArray(body.detail)
    ) {
      const messages = body.detail
        .map(validationDetailMessage)
        .filter((message): message is string => Boolean(message));
      if (messages.length > 0) return messages.join("; ");
    }
  } catch {
    return message;
  }

  return message;
}

function validationDetailMessage(detail: unknown): string | null {
  if (!detail || typeof detail !== "object") return null;

  const record = detail as Record<string, unknown>;
  if (typeof record.msg !== "string") return null;

  const field = validationDetailField(record.loc);
  return field ? `${field}: ${record.msg}` : record.msg;
}

function validationDetailField(location: unknown): string | null {
  if (!Array.isArray(location)) return null;

  for (let index = location.length - 1; index >= 0; index -= 1) {
    const part = location[index];
    if (typeof part === "string" && part !== "body" && part !== "query") {
      return part;
    }
  }
  return null;
}

function startsWithJsonObject(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    if (
      character !== " " &&
      character !== "\n" &&
      character !== "\r" &&
      character !== "\t"
    ) {
      return character === "{";
    }
  }
  return false;
}

export async function fetchTaxYears(): Promise<number[]> {
  const response = await requestJson<unknown>("/api/tax-years");
  if (!isTaxYearsResponse(response)) {
    throw new Error("Malformed tax year response");
  }
  return response.years;
}

export async function fetchFilingStatuses(year: number): Promise<FilingStatus[]> {
  const response = await requestJson<unknown>(
    `/api/tax-years/${year}/filing-statuses`
  );
  if (!isFilingStatusesResponse(response)) {
    throw new Error("Malformed filing status response");
  }
  return response.statuses;
}

function isTaxYearsResponse(value: unknown): value is { years: number[] } {
  return (
    isRecord(value) &&
    Array.isArray(value.years) &&
    value.years.every((year) => Number.isInteger(year) && year >= 0)
  );
}

function isFilingStatusesResponse(
  value: unknown
): value is { statuses: FilingStatus[] } {
  return (
    isRecord(value) &&
    Array.isArray(value.statuses) &&
    value.statuses.every(isFilingStatus)
  );
}

function isFilingStatus(value: unknown): value is FilingStatus {
  return (
    isRecord(value) &&
    typeof value.code === "string" &&
    typeof value.label === "string"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
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
    include_employer_payroll_tax: String(request.includeEmployerPayrollTax),
    include_marginal_breakpoints: String(request.includeMarginalBreakpoints ?? false),
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
