# Tax Explorer

React and Python tools for exploring US tax burden across income levels.

The initial model targets tax year 2026 for W-2 wage income and supports single,
married filing jointly, married filing separately, and head of household filing
statuses. It applies the standard deduction for the selected filing status,
calculates federal income tax, employee FICA taxes, Additional Medicare Tax, and
an optional employer payroll tax view. Tax parameters are stored in SQLite and
served through a FastAPI backend.

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
- `GET /api/income-series?year=2026&filing_status=married_joint&start=0&stop=500000&step=10000`

The local SQLite database is created and seeded at `data/tax_explorer.sqlite3`
when the API starts. Set `TAX_EXPLORER_DB=/path/to/file.sqlite3` to override the
database path.

## Current Scope

The model currently assumes:

- Tax year 2026
- US federal tax only
- Filing statuses: single, married filing jointly, married filing separately,
  and head of household
- Standard deduction only for the selected filing status
- Wage income subject to employee FICA payroll taxes
- No credits, itemized deductions, state taxes, local taxes, AMT, NIIT, or
  self-employment tax

## Sources

- IRS 2026 inflation adjustments for federal income tax brackets and standard
  deduction: https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2026-including-amendments-from-the-one-big-beautiful-bill
- IRS Revenue Procedure 2025-32, including 2026 tax rate tables and standard
  deduction amounts: https://www.irs.gov/pub/irs-drop/rp-25-32.pdf
- IRS Publication 15 (2026) for Social Security, Medicare, and Additional
  Medicare withholding rates and thresholds: https://www.irs.gov/publications/p15
