# Tax Explorer

Python tools for exploring US tax burden across income levels.

The initial model targets tax year 2026 for a single filer taking the standard
deduction. It calculates federal income tax, employee FICA taxes, Additional
Medicare Tax, and an optional employer payroll tax view.

## Usage

Run the tests:

```bash
uv run --extra dev pytest
```

Generate sampled income rows as CSV:

```bash
uv run tax-explorer --start 0 --stop 500000 --step 10000
```

Include employer-side Social Security and Medicare taxes:

```bash
uv run tax-explorer --start 0 --stop 500000 --step 10000 --include-employer-payroll-tax
```

## Current Scope

The model currently assumes:

- Tax year 2026
- US federal tax only
- Single filer
- Standard deduction
- Wage income subject to employee FICA payroll taxes
- No credits, itemized deductions, state taxes, local taxes, AMT, NIIT, or
  self-employment tax

## Sources

- IRS 2026 inflation adjustments for federal income tax brackets and standard
  deduction: https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2026-including-amendments-from-the-one-big-beautiful-bill
- IRS Publication 15 (2026) for Social Security, Medicare, and Additional
  Medicare withholding rates and thresholds: https://www.irs.gov/publications/p15
