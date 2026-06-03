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
};

export type TaxParameters = {
  federal: FederalParameters;
  payroll: PayrollParameters;
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
  employer_social_security_tax: string;
  employer_medicare_tax: string;
  total_employer_payroll_tax: string;
  total_tax_with_employer_payroll: string;
};

export type IncomeSeriesResponse = {
  rows: TaxBurden[];
};
