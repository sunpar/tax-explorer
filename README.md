# Tax Explorer

React and Python tools for exploring US tax burden across income levels.

The model targets tax year 2026 for W-2 wage income and supports single, married
filing jointly, married filing separately, and head of household filing
statuses. It applies the standard deduction for the selected filing status,
models employee pre-tax deductions, calculates federal income tax, employee FICA
taxes, Additional Medicare Tax, and an optional employer payroll tax view. Tax
parameters are stored in SQLite and served through a FastAPI backend.
The app breaks total tax into federal income tax, Social Security tax, Medicare
tax, Additional Medicare tax, and optional employer payroll tax components.

## Usage

Install backend dependencies and run the tests:

```bash
uv sync --extra dev
uv run python -m pytest
```

Generate sampled income rows as CSV:

```bash
uv run tax-explorer --start 0 --stop 500000 --step 10000
```

Include employer-side Social Security and Medicare taxes:

```bash
uv run tax-explorer --start 0 --stop 500000 --step 10000 --include-employer-payroll-tax
```

Use the gradual deduction phase-in model:

```bash
uv run tax-explorer --start 0 --stop 500000 --step 10000 --pretax-deduction-mode gradual_phase_in
```

Include dependent-care FSA modeling for filers with dependents:

```bash
uv run tax-explorer --start 0 --stop 500000 --step 10000 --dependent-count 1
```

Model married-joint dual earners and include exact marginal-rate change rows:

```bash
uv run tax-explorer --filing-status married_joint --secondary-income 150000 --include-marginal-breakpoints
```

Run the API:

```bash
uv run python -m uvicorn tax_explorer.api:app --reload
```

Run the React app in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` requests to `http://127.0.0.1:8000`.

Build the frontend:

```bash
cd frontend
npm run build
```

## API

- `GET /api/tax-years`
- `GET /api/tax-years/{year}/filing-statuses`
- `GET /api/tax-years/{year}/parameters?filing_status=head_of_household`
- `POST /api/calculate`
- `GET /api/income-series?year=2026&filing_status=married_joint&start=0&stop=500000&step=10000&dependent_count=1&secondary_income=50000&pretax_deduction_mode=max_available`

API request and response field names use snake_case. Monetary and rate values
are serialized as strings to preserve decimal precision. Payroll parameter
responses include both `additional_medicare_threshold_single` for legacy callers
and `additional_medicare_thresholds`, keyed by filing status, for selected-status
Additional Medicare Tax calculations.

The default `pretax_deduction_mode` is `max_available`, which uses active
employee 401(k), health FSA, and dependent-care FSA caps as income allows.
Dependent-care FSA is active when `dependent_count` is greater than zero; married
filing separately uses half of the configured dependent-care cap. The alternate
`gradual_phase_in` mode starts at the selected filing status standard deduction
and ramps deductions from 1% of gross income until the active caps are maxed.
For married filing jointly, `secondary_income` can model a second earner inside
the total household gross income. When it is greater than zero, Social Security
tax is capped separately per earner, employee 401(k) and health FSA caps double,
and the gradual phase-in endpoint for the duplicated worker caps is extended to
roughly 150% of the one-earner max-out income.

The local SQLite database is created and seeded at `data/tax_explorer.sqlite3`
on the first database-backed API request. Set
`TAX_EXPLORER_DB=/path/to/file.sqlite3` to override the database path.

## Current Scope

The model currently assumes:

- Tax year 2026
- US federal tax only
- Filing statuses: single, married filing jointly, married filing separately,
  and head of household
- Standard deduction for the selected filing status
- Employee 401(k), health FSA, and dependent-care FSA pre-tax deduction modeling
- Optional married-joint second income for per-earner Social Security caps and
  doubled worker-specific 401(k) and health FSA limits
- Wage income subject to employee FICA payroll taxes
- No credits, itemized deductions, state taxes, local taxes, AMT, NIIT, or
  self-employment tax
- No dependent-care qualified-expense validation, spouse earned-income constraint
  checks, or age-based 401(k) catch-up limits yet

## Sources

- IRS 2026 inflation adjustments for federal income tax brackets and standard
  deduction: https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2026-including-amendments-from-the-one-big-beautiful-bill
- IRS Revenue Procedure 2025-32, including 2026 tax rate tables and standard
  deduction amounts: https://www.irs.gov/pub/irs-drop/rp-25-32.pdf
- IRS Publication 15 (2026) for Social Security, Medicare, and Additional
  Medicare withholding rates and thresholds: https://www.irs.gov/publications/p15
- IRS retirement topic on 401(k) elective deferral limits:
  https://www.irs.gov/retirement-plans/plan-participant-employee/retirement-topics-contributions
- IRS Internal Revenue Bulletin 2025-45 for 2026 standard deduction and health
  FSA limits: https://www.irs.gov/irb/2025-45_IRB
- IRS summary of business tax provisions from the One Big Beautiful Bill for the
  dependent care assistance program exclusion increase:
  https://www.irs.gov/newsroom/one-big-beautiful-bill-business-tax-provisions-youtube-video-text-script
