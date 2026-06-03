# FastAPI React SQLite Tax Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Tax Explorer into a React single-page app backed by FastAPI, with tax-year parameters stored in SQLite and served through API endpoints.

**Architecture:** Keep tax calculation in Python and move tax parameters out of hardcoded defaults into a SQLite repository. FastAPI exposes tax-year metadata, parameters, one-off calculations, and sampled income-series data. The React/Vite frontend fetches API data and renders an interactive tax-burden chart and summary table.

**Tech Stack:** Python 3.11+, FastAPI, sqlite3, pytest, React, TypeScript, Vite, Recharts.

---

### Task 1: SQLite Tax Parameter Store

**Files:**
- Create: `src/tax_explorer/database.py`
- Create: `tests/test_database.py`
- Modify: `src/tax_explorer/__init__.py`
- Modify: `pyproject.toml`

- [ ] Write tests proving a fresh SQLite database can be initialized and queried for 2026 single-filer federal and payroll parameters.
- [ ] Run `uv run --extra dev pytest tests/test_database.py -v` and verify the tests fail because the database module does not exist.
- [ ] Implement schema creation, idempotent seed data, and query helpers using standard-library `sqlite3`.
- [ ] Run `uv run --extra dev pytest tests/test_database.py tests/test_tax_2026.py -v` and verify all tests pass.

### Task 2: FastAPI Backend

**Files:**
- Create: `src/tax_explorer/api.py`
- Create: `tests/test_api.py`
- Modify: `pyproject.toml`
- Modify: `README.md`

- [ ] Write API tests for `GET /api/tax-years`, `GET /api/tax-years/2026/parameters`, `POST /api/calculate`, and `GET /api/income-series`.
- [ ] Run `uv run --extra dev pytest tests/test_api.py -v` and verify the tests fail because the API module does not exist.
- [ ] Implement a FastAPI app that initializes the SQLite database on startup and returns JSON-safe decimal values.
- [ ] Run `uv run --extra dev pytest tests/test_api.py tests/test_database.py tests/test_tax_2026.py -v` and verify all tests pass.

### Task 3: React Single-Page App

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/App.css`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/types.ts`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Modify: `.gitignore`
- Modify: `README.md`

- [ ] Scaffold a Vite React app in `frontend/`.
- [ ] Implement API helpers that call the FastAPI endpoints through the Vite `/api` proxy.
- [ ] Build an interactive app with year, income range, step, and employer-payroll controls.
- [ ] Render a line chart for total employee tax and effective tax rate, plus a selected-income summary and table.
- [ ] Run `npm install`, `npm run build`, and `npm run test` if a test script is present.

### Task 4: End-to-End Verification

**Files:**
- Modify only if verification finds defects.

- [ ] Run `uv run --extra dev pytest`.
- [ ] Run `uv run uvicorn tax_explorer.api:app --reload` locally.
- [ ] Run the Vite dev server and verify the SPA loads through the API proxy.
- [ ] Use browser verification for desktop and mobile viewports.
- [ ] Confirm `git status -sb` contains only intentional changes.
- [ ] Commit and push the implementation to `origin/main`.
