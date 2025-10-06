# Repository Guidelines

## Project Structure & Module Organization
- `app.py`: Streamlit entrypoint. UI pages live in `pages/`.
- Core modules: `config.py` (DB config/sync), `db_handler.py`, `doctrines.py`, `models.py`, `utils.py`.
- Data/assets: local SQLite/LibSQL replicas (`*.db*`), CSV seeds, and logs (ignored by Git).
- Docs: `docs/` contains admin/database guides and walkthroughs.
- Config: `.streamlit/` for secrets, `.env` for local overrides.
- Tests: lightweight checks in `tests/` (note: directory is ignored by `.gitignore`).

## Build, Test, and Development Commands
- Install deps (Python 3.12 via uv): `uv sync`
- Run app locally: `uv run streamlit run app.py`
- Lint/format (recommended): `uv run ruff check .` and `uv run ruff format .` (add Ruff if not installed).
- Quick data scripts: `uv run python build_cost_models.py` (rebuilds cost DB), others run similarly.

## Coding Style & Naming Conventions
- Python style: PEP 8, 4‑space indents, max line length 100.
- Naming: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- Types/docstrings: prefer type hints; include concise docstrings on public functions.
- Logging: use `logging` with `logging_config.py`; don’t print() in production code.

## Testing Guidelines
- Framework: add `pytest` for new tests; place files under `tests/` named `test_*.py`.
- What to test: data shape/columns, query correctness, and page-level helpers (mock DB where possible).
- Run (after adding pytest): `uv run pytest -q`.

## Commit & Pull Request Guidelines
- Commits: follow Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`). Keep focused, imperative mood.
- PRs: include a clear summary, linked issues, steps to validate, and screenshots/GIFs for UI changes. Note any DB/schema or config impacts.

## Security & Configuration Tips
- Secrets: store Turso URLs/tokens in `.streamlit/secrets.toml`; never hard‑code.
- Local env: `.env` supported by `python-dotenv`.
- Git hygiene: large `*.db*` and `*.log` files are ignored—avoid committing generated artifacts.

## Architecture Overview (Brief)
- Streamlit frontend (`app.py` + `pages/`) backed by local LibSQL replicas synced from Turso via `DatabaseConfig`. Business logic stays in modules; UI files should remain thin and delegate to helpers.

## Recent Features

### Tech II Invention Cost Calculator (COMPLETED)
Integrated invention cost calculations into the Build Cost Tool (`pages/build_costs.py`).

**Key Components:**
- **T2 Detection**: Automatic identification via `is_t2_item()` querying SDE database (`metaGroupID = 2`)
- **T1 Blueprint Lookup**: `get_t1_blueprint_for_t2_item()` queries EVE Ref API to find the T1 blueprint required for invention
- **Decryptor Support**: All 9 decryptor types (8 + None) with configurable selection
- **Skill Configuration**: 10 skill inputs (Science, Advanced Industry, Industry, 7 Encryption Methods)
- **Structure Selection**: Separate invention structure with default to "4-HWWF - WinterCo. Laboratory Center"

**Calculation Flow (T2 Items):**
1. **Invention calculated FIRST** → determines ME/TE of invented BPC
2. ME/TE extracted from selected decryptor's results
3. **Manufacturing calculated** with correct decryptor-specific ME/TE
4. Combined costs displayed (Invention + Manufacturing)

**API Integration:**
- Invention endpoint: `https://api.everef.net/v1/industry/cost` (blueprint_id param)
- Async fetching for all 9 decryptors (4-6 concurrent requests)
- Response parsing: probability, runs_per_copy, ME/TE, material costs, avg_cost_per_unit

**UI Features:**
- **Sidebar Controls**:
  - ME/TE inputs disabled for T2 (shows info message)
  - Invention Structure selector (collapsible expander)
  - Decryptor Selection: Auto (Best Cost) or specific decryptor
  - Skills Configuration (collapsible expander with 10 skill sliders)
- **Results Display**:
  - Decryptor comparison table (9 rows with success %, costs, ME/TE, highlighting)
  - Key metrics (Best Cost/Unit, Highest Success Rate, Expected Units)
  - Material breakdown per decryptor (interactive selector)
  - Manufacturing table includes invention cost columns for T2 items
- **Cost Integration**:
  - `invention_cost_per_unit` column added to manufacturing dataframe
  - `total_production_cost_per_unit` = Manufacturing + Invention
  - `total_production_cost` = Combined cost for all units
  - Profit margins automatically use combined cost for T2 items
- **ME/TE Display**:
  - T2 items show: "📋 Manufacturing BPC: ME X / TE Y from [Decryptor] (Invented BPC)"
  - Clear indication of which decryptor's ME/TE is being used

**Technical Implementation:**
- `DECRYPTORS` constant: Maps decryptor names to type IDs (34201-34208)
- `JobQuery` dataclass extended with invention fields (skills, structure, decryptor)
- `construct_invention_url()`: Builds API URLs (no structure_type_id/rig_id for invention)
- `get_invention_costs_async()`: Fetches costs for all decryptors in parallel
- `fetch_one_invention()`: Parses individual decryptor response
- `display_invention_costs()`: Renders comparison table and material breakdown

**Session State:**
- `invention_costs`: Dict of decryptor_name → cost_data
- `selected_invention_structure`: Structure name for invention
- `selected_decryptor_for_costs`: User's decryptor choice (or "Auto")
- `manufacturing_me`, `manufacturing_te`, `me_te_source`: Tracks BPC stats for display
- Skill levels: 10 session state variables (defaults to 5)

**Files Modified:**
- `pages/build_costs.py`: Main implementation (~400 lines added)
- Session state initialization extended with invention-specific variables
- `display_data()` updated to show invention columns for T2 items

**Documentation:**
- `INVENTION_SUMMARY.md`: Feature overview and user-facing documentation
- `INVENTION_COST_IMPLEMENTATION_PLAN.md`: Detailed implementation phases
- `INVENTION_TECHNICAL_REFERENCE.md`: API specs and data structures

**Testing:**
- Test scripts created: `test_invention_simple.py`, `test_invention_api.py`, `test_t1_blueprint_lookup.py`
- Verified API integration and T1 blueprint lookup functionality
- Confirmed decryptor selection affects manufacturing ME/TE and cost calculations

## TODOs
✅ COMPLETED - Refactored concurrency handling to use read-write locks (RWLock) instead of exclusive locks
  - Multiple concurrent reads now allowed
  - Writers maintain exclusive access
  - Sync operations properly block all access
  - Added comprehensive test coverage (12 new tests)

✅ COMPLETED - Updated tests to reflect current state of the codebase
  - All 36 tests passing (24 existing + 12 new)
  - Added test_rwlock.py for RWLock implementation
  - Added test_database_config_concurrency.py for DatabaseConfig concurrency behavior

✅ COMPLETED - Invention Cost Calculator Feature
  - T2 item detection and T1 blueprint lookup
  - All 9 decryptor cost calculations
  - ME/TE correctly sourced from invented BPC
  - Combined production costs (invention + manufacturing)
  - Comprehensive UI with comparison tables and material breakdowns
  - Profit calculations include invention costs
