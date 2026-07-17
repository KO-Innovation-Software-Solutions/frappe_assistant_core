# Session Summary

## Problem
The `@openuidev/lang-core` parser silently produces `root: null, statementCount: 0` for ALL DSL input, with no errors.

## Root Cause
The parser's `split()` function (line 1922 in `index.mjs`) requires statements in `identifier = expression` format — it checks for token type 9 (`=`) after the identifier. Bare component calls like `Stack([...])` are skipped because the token after `Stack` is `(` (type 1), not `=`.

## Fixes Applied

### Fix 1: Parser format (previous session)

#### Frontend (`context.jsx`)
Added `normalizeDsl()` function that:
- Strips markdown code fences (`` ``` ``)
- Strips language tags (e.g., `` ```openui_lang ``)
- Returns the code as-is if it already has `identifier = ...` prefix
- Otherwise prepends `response = ` to the code

#### Backend (`system_prompt.py`)
Added a rule telling the LLM: "Always output your response using the format: `response = RootComponent([...])`".

### Fix 2: LLM uses plain tables/text instead of styled KPI/Card components (current session)

#### Root Cause
The `_render_as_openui()` system prompt rules never told the LLM to prefer Card-based KPIs for single-metric summaries, or to wrap data in Cards. The LLM defaulted to `Table`/`TextContent` for everything. Additionally, `_render_as_openui()` swallowed all exceptions silently (returning `None`), causing the frontend to fall back to plain text.

#### Changes

**`system_prompt.py`** — Added explicit KPI & data display rules:
- Single-metric summaries → `Card([CardHeader(title), TextContent(value, "large-heavy")])`
- Multiple KPIs side by side → `Stack(direction="row", [Card(...), Card(...)])`
- Always wrap structured data in Card components
- Never output bare Table/TextContent at root level
- Never render as raw HTML, markdown, or ASCII

**`openai.py` / `ollama.py`** — Improved `_render_as_openui()`:
- Simplified render instruction with a concrete example
- Instructs model to output ONLY the component expression (no fences, no explanation)
- Validates output contains DSL tokens before returning
- Logs non-DSL output as warnings and errors (previously silent failure)
- Returns `None` only when output is clearly not DSL

**`context.jsx`** — Strengthened `normalizeDsl()`:
- Handles multi-line output: scans lines for `identifier =` prefix or component call
- Fixes "response=..." without spaces: normalizes to `response = ...`
- Recognizes component calls mid-text and extracts them

### Fix 3: Variable name mismatch — `response =` vs `root =` (this session)

#### Root Cause
The parser (`@openuidev/lang-core`) has `DEFAULT_ROOT_STATEMENT_ID = "root"` and looks for `result.root` in parsed output. The error hint says `"starting with root = ${library.root}(...)"`. But `normalizeDsl()` in `context.jsx` prepended `response =`, and `_render_as_openui` instructed the model to use `response =`. The parser's `pickEntryId()` has a tertiary fallback that matches by component type name (e.g., `Stack`), but the primary path looks for a variable named `root`.

#### Changes

**`context.jsx`** — `normalizeDsl()` fallbacks now prepend `"root = "` instead of `"response = "`.

**`system_prompt.py`** — Changed rule from `` `response = RootComponent([...])` `` to `` `root = RootComponent([...])` ``. Added CRITICAL OUTPUT RULES block:
- Always valid UI — no plain text, ASCII art, or markdown tables
- Charts are DSL components (BarChart, LineChart, PieChart) — not tools — always use them on request
- KpiCard for single-metric summaries
- DataTable for tabular data (not generic Table)
- Stack(direction="row") for side-by-side layout
- Every response assigns to `root` variable exactly
- No empty containers

**`openai.py` / `ollama.py`** — `_render_as_openui()`:
- Render instruction now uses `root =` instead of `response =`
- Added example for multi-line Fleet Overview format
- CRITICAL: Every text content must be wrapped in a component — never bare text as Stack/Card child
- Validation now checks for `"root ="` only (stricter)
