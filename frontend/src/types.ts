export type FederalBracket = {
  lower_bound: string;
  rate: string;
};

export type FederalParameters = {
  tax_year: number;
  filing_status: string;
  standard_deduction: string;
  brackets: FederalBracket[];
};

export type PayrollParameters = {
  tax_year: number;
  social_security_rate: string;
  social_security_wage_base: string;
  medicare_rate: string;
  additional_medicare_rate: string;
  additional_medicare_threshold_single: string;
  additional_medicare_thresholds: Record<string, string>;
};

export type PretaxDeductionParameters = {
  tax_year: number;
  employee_401k_limit: string;
  health_fsa_limit: string;
  dependent_care_fsa_limit: string;
  gradual_phase_in_start_rate: string;
};

export type TaxParameters = {
  federal: FederalParameters;
  payroll: PayrollParameters;
  pretax_deductions: PretaxDeductionParameters;
};

export type FilingStatus = {
  code: string;
  label: string;
};

export type TaxBreakdownItem = {
  code: string;
  label: string;
  amount: string;
};

export type PayrollBreakdownItem = {
  label: string;
  gross_income: string;
  payroll_wages: string;
  employee_social_security_tax: string;
  employee_medicare_tax: string;
  employee_additional_medicare_tax: string;
  total_employee_payroll_tax: string;
  employer_social_security_tax: string;
  employer_medicare_tax: string;
  total_employer_payroll_tax: string;
  total_payroll_tax: string;
};

export type TaxBurden = {
  gross_income: string;
  taxable_income: string;
  federal_income_tax: string;
  employee_social_security_tax: string;
  employee_medicare_tax: string;
  employee_additional_medicare_tax: string;
  total_employee_payroll_tax: string;
  total_employee_tax: string;
  effective_employee_tax_rate: string;
  marginal_employee_tax_rate: string;
  employee_401k_contribution: string;
  health_fsa_contribution: string;
  dependent_care_fsa_contribution: string;
  total_pretax_deductions: string;
  employer_social_security_tax: string;
  employer_medicare_tax: string;
  total_employer_payroll_tax: string;
  total_tax_with_employer_payroll: string;
  marginal_tax_rate_with_employer_payroll: string;
  payroll_breakdown: PayrollBreakdownItem[];
  tax_breakdown: TaxBreakdownItem[];
};

export type IncomeSeriesResponse = {
  rows: TaxBurden[];
};
