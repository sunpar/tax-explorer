import type {
  FederalBracket,
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

type TaxBurdenDecimalField = Exclude<
  keyof TaxBurden,
  "payroll_breakdown" | "tax_breakdown"
>;
type PayrollBreakdownItem = TaxBurden["payroll_breakdown"][number];
type TaxBreakdownItem = TaxBurden["tax_breakdown"][number];
type PayrollBreakdownDecimalField = Exclude<
  keyof PayrollBreakdownItem,
  "label"
>;

const DECIMAL_STRING_PATTERN = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/;
const TAX_BURDEN_DECIMAL_FIELDS = [
  "gross_income",
  "taxable_income",
  "federal_income_tax",
  "employee_social_security_tax",
  "employee_medicare_tax",
  "employee_additional_medicare_tax",
  "total_employee_payroll_tax",
  "total_employee_tax",
  "effective_employee_tax_rate",
  "marginal_employee_tax_rate",
  "employee_401k_contribution",
  "health_fsa_contribution",
  "dependent_care_fsa_contribution",
  "total_pretax_deductions",
  "employer_social_security_tax",
  "employer_medicare_tax",
  "total_employer_payroll_tax",
  "total_tax_with_employer_payroll",
  "marginal_tax_rate_with_employer_payroll"
] as const satisfies readonly TaxBurdenDecimalField[];
const PAYROLL_BREAKDOWN_DECIMAL_FIELDS = [
  "gross_income",
  "payroll_wages",
  "employee_social_security_tax",
  "employee_medicare_tax",
  "employee_additional_medicare_tax",
  "total_employee_payroll_tax",
  "employer_social_security_tax",
  "employer_medicare_tax",
  "total_employer_payroll_tax",
  "total_payroll_tax"
] as const satisfies readonly PayrollBreakdownDecimalField[];

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
  if (!isRecord(value) || !Array.isArray(value.years)) return false;

  const { years } = value;
  return years.every((year, index) => {
    if (!Number.isInteger(year) || year < 0) return false;
    return index === 0 || year > years[index - 1];
  });
}

function isFilingStatusesResponse(
  value: unknown
): value is { statuses: FilingStatus[] } {
  if (!isRecord(value) || !Array.isArray(value.statuses)) return false;
  if (value.statuses.length === 0) return false;

  const codes = new Set<string>();
  for (const status of value.statuses) {
    if (!isFilingStatus(status) || codes.has(status.code)) return false;
    codes.add(status.code);
  }
  return true;
}

function isFilingStatus(value: unknown): value is FilingStatus {
  return (
    isRecord(value) &&
    isNonBlankString(value.code) &&
    isNonBlankString(value.label)
  );
}

function isTaxParameters(
  value: unknown,
  year: number,
  filingStatus: string
): value is TaxParameters {
  return (
    isRecord(value) &&
    isFederalParameters(value.federal, year, filingStatus) &&
    isPayrollParameters(value.payroll, year) &&
    isPretaxDeductionParameters(value.pretax_deductions, year) &&
    hasSelectedAdditionalMedicareThreshold(value.payroll, filingStatus)
  );
}

function isFederalParameters(
  value: unknown,
  year: number,
  filingStatus: string
): value is TaxParameters["federal"] {
  return (
    isRecord(value) &&
    value.tax_year === year &&
    value.filing_status === filingStatus &&
    isDecimalString(value.standard_deduction) &&
    isFederalBrackets(value.brackets)
  );
}

function isFederalBrackets(value: unknown): value is FederalBracket[] {
  if (!Array.isArray(value) || value.length === 0) return false;
  if (!value.every(isFederalBracket)) return false;
  if (Number(value[0].lower_bound) !== 0) return false;

  for (let index = 1; index < value.length; index += 1) {
    if (Number(value[index].lower_bound) <= Number(value[index - 1].lower_bound)) {
      return false;
    }
  }
  return true;
}

function isFederalBracket(value: unknown): value is FederalBracket {
  return (
    isRecord(value) &&
    isDecimalString(value.lower_bound) &&
    isDecimalString(value.rate)
  );
}

function isPayrollParameters(
  value: unknown,
  year: number
): value is TaxParameters["payroll"] {
  return (
    isRecord(value) &&
    value.tax_year === year &&
    isDecimalString(value.social_security_rate) &&
    isDecimalString(value.social_security_wage_base) &&
    isDecimalString(value.medicare_rate) &&
    isDecimalString(value.additional_medicare_rate) &&
    isDecimalString(value.additional_medicare_threshold_single) &&
    isDecimalStringRecord(value.additional_medicare_thresholds)
  );
}

function isPretaxDeductionParameters(
  value: unknown,
  year: number
): value is TaxParameters["pretax_deductions"] {
  return (
    isRecord(value) &&
    value.tax_year === year &&
    isDecimalString(value.employee_401k_limit) &&
    isDecimalString(value.health_fsa_limit) &&
    isDecimalString(value.dependent_care_fsa_limit) &&
    isDecimalString(value.gradual_phase_in_start_rate)
  );
}

function hasSelectedAdditionalMedicareThreshold(
  value: TaxParameters["payroll"],
  filingStatus: string
): boolean {
  return (
    filingStatus === "single" ||
    Object.prototype.hasOwnProperty.call(
      value.additional_medicare_thresholds,
      filingStatus
    )
  );
}

function isDecimalStringRecord(value: unknown): value is Record<string, string> {
  return (
    isRecord(value) &&
    Object.values(value).every(isDecimalString)
  );
}

function isDecimalString(value: unknown): value is string {
  return (
    typeof value === "string" &&
    DECIMAL_STRING_PATTERN.test(value) &&
    Number.isFinite(Number(value))
  );
}

function hasDecimalStringFields(
  value: Record<string, unknown>,
  fields: readonly string[]
): boolean {
  return fields.every((field) => isDecimalString(value[field]));
}

function hasUniqueStringValues<T>(
  values: readonly T[],
  valueFor: (value: T) => string
): boolean {
  const seen = new Set<string>();
  for (const value of values) {
    const nextValue = valueFor(value);
    if (seen.has(nextValue)) return false;
    seen.add(nextValue);
  }
  return true;
}

function isTaxBurden(value: unknown): value is TaxBurden {
  if (
    !isRecord(value) ||
    !hasDecimalStringFields(value, TAX_BURDEN_DECIMAL_FIELDS)
  ) {
    return false;
  }
  if (
    !Array.isArray(value.payroll_breakdown) ||
    value.payroll_breakdown.length === 0
  ) {
    return false;
  }
  if (
    !Array.isArray(value.tax_breakdown) ||
    value.tax_breakdown.length === 0
  ) {
    return false;
  }

  const { payroll_breakdown: payrollBreakdown, tax_breakdown: taxBreakdown } =
    value;
  if (!payrollBreakdown.every(isPayrollBreakdownItem)) return false;
  if (!taxBreakdown.every(isTaxBreakdownItem)) return false;

  return (
    hasUniqueStringValues(payrollBreakdown, (row) => row.label) &&
    hasUniqueStringValues(taxBreakdown, (item) => item.code)
  );
}

function isPayrollBreakdownItem(value: unknown): value is PayrollBreakdownItem {
  return (
    isRecord(value) &&
    isNonBlankString(value.label) &&
    hasDecimalStringFields(value, PAYROLL_BREAKDOWN_DECIMAL_FIELDS)
  );
}

function isTaxBreakdownItem(value: unknown): value is TaxBreakdownItem {
  return (
    isRecord(value) &&
    isNonBlankString(value.code) &&
    isNonBlankString(value.label) &&
    isDecimalString(value.amount)
  );
}

function isIncomeSeriesResponse(value: unknown): value is IncomeSeriesResponse {
  return (
    isRecord(value) &&
    Array.isArray(value.rows) &&
    value.rows.length > 0 &&
    value.rows.every(isTaxBurden)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isNonBlankString(value: unknown): value is string {
  return typeof value === "string" && value.trim() !== "";
}

export async function fetchTaxParameters(
  year: number,
  filingStatus: string
): Promise<TaxParameters> {
  const params = new URLSearchParams({ filing_status: filingStatus });
  const response = await requestJson<unknown>(
    `/api/tax-years/${year}/parameters?${params.toString()}`
  );
  if (!isTaxParameters(response, year, filingStatus)) {
    throw new Error("Malformed tax parameter response");
  }
  return response;
}

export async function fetchIncomeSeries(
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
  const response = await requestJson<unknown>(
    `/api/income-series?${params.toString()}`
  );
  if (!isIncomeSeriesResponse(response)) {
    throw new Error("Malformed income series response");
  }
  return response;
}

export async function fetchTaxBurden(request: CalculateRequest): Promise<TaxBurden> {
  const response = await requestJson<unknown>("/api/calculate", {
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
  if (!isTaxBurden(response)) {
    throw new Error("Malformed tax burden response");
  }
  return response;
}
