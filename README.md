# Crypto Investigation Evidence Engine — MVP1

A local investigation workspace that makes evidence collection and reasoning visible. Choose FIXTURE for deterministic offline observations or LIVE for real Ethereum and Solana collection. Live public-source OSINT is available. With GEMINI_API_KEY configured, new LIVE cases use Gemini planning and evidence-grounded reasoning; fixture mode stays deterministic. Solana supports mixed-chain cases.

## Run locally (Windows PowerShell)

Prerequisites: Python 3.11+ and Node.js 22.12+ (Node 24 also works). Dependency installation requires internet access; FIXTURE mode runs offline after installation; LIVE mode requires provider network access.

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. If an older backend is already running, restart it to load the new lifecycle and API.

For LIVE mode, copy backend/.env.example to backend/.env (merge settings if it already exists), then restart the backend. The example uses the public Ethereum Blockscout v2 endpoint, validated without a key. For its PRO gateway, configure the documented URL and private bearer key in the environment. Never commit backend/.env.

Gemini reasoning is optional. To run reasoning locally with Ollama, install Ollama, run `ollama pull gemma3:4b`, and set `AI_PROVIDER=ollama` in `backend/.env`; the local defaults use `http://127.0.0.1:11434` and `gemma3:4b`. Gemini remains available with `AI_PROVIDER=gemini` and `GEMINI_API_KEY`.

The start screen accepts 1–10 Ethereum or Solana wallet addresses in LIVE mode and a required investigation question. The development example is prefilled. Choose the data mode and click **Start investigation**. In FIXTURE mode, run the source check. In LIVE mode, select a wallet in the graph, then **Expand inbound**, **Expand outbound**, or **Inspect counterparty**. All pivots add evidence to the same case. New evidence appears before the revised assessment and next recommendation.

SQLite is created automatically at `backend/data/investigations.sqlite3`. Optional configuration: copy `backend/.env.example` to `backend/.env` and set `DATABASE_PATH`. Use one backend process. The URL preserves the investigation ID; refreshing resumes it.

Health: http://127.0.0.1:8000/health

API documentation: http://127.0.0.1:8000/docs

On macOS/Linux, replace `.venv\Scripts\python.exe` with `.venv/bin/python` and use forward slashes. No virtual environment activation is required. Dependency ranges are in `backend/requirements.txt`; the lock file records the tested environment.

## What the application does

The persisted lifecycle is:

```text
CREATED → PLANNING → COLLECTING → ANALYZING → AWAITING_ACTION
                                                ↓
                                        EXECUTING_ACTION
                                                ↓
                                          REANALYZING
                                                ↓
                                      AWAITING_ACTION / COMPLETE
```

Failed operations enter `ERROR` and can retry from the saved operation. Completing the available actions does not mean all unknowns are resolved.

- The selected planner uses the question to prioritize collection steps and explain their purpose; Gemini is enabled for new LIVE cases when configured.
- Fixture, live Ethereum, and live Solana tools return observations. The evidence service validates and normalizes provenance; tools never create conclusions.
- The reasoning engine creates evidence-linked FACT, INFERENCE and UNKNOWN claims and competing explanations.
- The action engine derives the important unknown and ranks executable candidate actions using the documented weights. Live candidates follow discovered addresses; fixture candidates retain the original three demonstration steps.
- The workspace combines a Cytoscape graph, transfer ledger, evidence inspectors, explanation panels, contradictions, gaps, fragility and a recommended step.
- Each action collects new evidence, reevaluates the case and saves a revision describing evidence, claims, explanation support, unknowns and recommendation changes.
- Activity events, plan steps, state, evidence and revision history persist in SQLite. Version checks prevent duplicate advancement; duplicate evidence and unchanged reanalysis do not create spurious revisions.
- In FIXTURE mode, addresses without local observations receive explicit coverage unknowns. The app does not invent transfers or explanations for them.

In the development case, initial collection produces 6 evidence records and 2 explanations. The source check adds a seventh record: it finds no independent ownership proof. Attribution becomes disputed, common-control support weakens, and the next recommendation becomes tracing Counterparty B. Later actions add a downstream transfer and document the remaining bridge gap.

## Tests and build

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests -q
cd frontend
npm run build
npx playwright install chromium
npm test
```

`npm run build` includes TypeScript checking. Playwright starts fresh test servers on backend port **8010** and frontend port **5174**; keep those ports free. It does not reuse the normal development servers. API tests use temporary databases; browser tests use an in-memory database and an injected offline provider. No automated test needs network access or an API key. Screenshots go to `frontend/test-results/`.

Tests cover lifecycle transitions, meaningful action changes, input validation, tool failure/retry, evidence deduplication, no-op reanalysis, concurrent duplicate requests, restart recovery, provenance inspectors, accessible controls and desktop/mobile layout. Browser tests also hold real API operations at collection and reanalysis boundaries to check intermediate evidence and revision states.

The Vite development server proxies `/api` to FastAPI. A production deployment would need to serve the built frontend and reverse-proxy `/api`; `npm run preview` alone is not the documented full-stack runtime.

## API

Routes below are backend routes. The frontend accesses them through Vite's `/api` prefix.

Create a case with the explicit mode below (omitting mode preserves the fixture default):

```json
{
  "mode": "live",
  "seeds": ["0x629e7Da20197a5429d30da36E77d06CdF796b71A"],
  "question": "What activity is this wallet associated with, and what evidence exists about where the funds came from and where they went?"
}
```

| Method | Route | Behavior |
| --- | --- | --- |
| POST | /investigations | Save inputs and return CREATED; no preloaded conclusions |
| GET | /investigations/{id} | Workspace, graph, current analysis, plan, events and revisions |
| POST | /investigations/{id}/advance | Perform one operation with body `{"expected_version": n}` |
| POST | /investigations/{id}/plan | Generate the plan from CREATED; same version body |
| POST | /investigations/{id}/collect | Advance one collection operation; same version body |
| POST | /investigations/{id}/ingest | Alias for collect |
| POST | /investigations/{id}/analyze | Request reanalysis of a settled case; unchanged input is a no-op |
| POST | /investigations/{id}/retry | Resume an ERROR state |
| POST | /investigations/{id}/actions/{action_id}/execute | Start an action (202); subsequent advances collect and reanalyze |
| GET | /investigations/{id}/graph | Cytoscape graph elements |
| GET | /investigations/{id}/{collection} | plan, events, evidence, claims, hypotheses, actions or revisions |
| POST | /investigations/{id}/expand | Execute a same-case pivot: entity_id plus direction (inbound, outbound, inspect) |
| GET | /investigations/{id}/entities/{entity_id}/history | Paginated collected history and address summaries; offset and limit |
| POST | /investigations/{id}/osint | Attach supplied URL/title/text/source_type; URL is never fetched |

API clients continue advancing using each response's version until AWAITING_ACTION, COMPLETE or ERROR. The browser does this automatically and renders each response. Request pacing only makes operations readable; backend results determine progress.

## File map and integration boundaries

```text
backend/app/
  models/domain.py          # Investigation, Entity, TransactionEvent, Evidence,
                            # Claim, Hypothesis, InvestigativeAction and Case
  models/workflow.py        # Plans, events, unknowns, revisions and advance request
  schemas/requests.py       # Seed/question and manual evidence validation
  services/orchestrator.py  # Generic persisted lifecycle and operation recovery
  services/planning.py      # Planner interface and deterministic implementation
  services/tools.py         # InvestigationTool, registry and three mock tools
  services/evidence.py      # Normalization, provenance validation and deduplication
  services/reasoning.py     # Reasoning interface and evidence-conditioned mock rules
  services/actions.py       # Candidate generation and important unknown
  services/revisions.py     # Assessment snapshots and revision differences
  services/scoring.py       # Action ranking and structural fragility
  services/graph.py         # NetworkX/Cytoscape graph projection
  services/osint.py         # Supplied text observation, no fetching
  services/ethereum.py      # Original fixture interface, retained for compatibility
  services/ethereum_provider.py # Provider protocol, environment settings, offline test provider
  services/blockscout.py    # Real HTTP transport and vendor-specific normalization
  services/ethereum_tool.py # Live evidence, summaries and pivots
  services/live_reasoning.py # Deterministic live planning, reasoning and actions
  services/gemini.py        # Gemini REST client, validation, planning and reasoning
  services/investigation.py # Orchestrator compatibility export
  repositories/sqlite.py    # Durable snapshot repository
  api/routes.py
  main.py
backend/tests/test_mvp.py
backend/tests/test_ethereum.py
backend/tests/browser_app.py
backend/tests/fixtures/wormhole_mock.json
frontend/src/
  pages/App.tsx
  components/InvestigationActivity.tsx
  components/Graph.tsx
  components/CaseAnalysis.tsx
  components/Decisions.tsx
  components/EvidenceDrawer.tsx
  components/EntityInspector.tsx
  components/ui.tsx
  hooks/useInvestigation.ts
  services/api.ts
  services/presentation.ts
  types/index.ts
  main.tsx
  styles.css
frontend/tests/workspace.spec.ts
frontend/playwright.config.ts
frontend/vite.config.ts
tests/fixtures/wormhole_mock.json
docs/architecture.md
docs/demo_case.md
```

Backend dependency/configuration files and frontend package, lock, TypeScript and Vite configuration complete the repository. The pre-existing root `main.py` and `.codex/config.toml` are untouched.

`MockEthereumTool` supplies transfers, protocol observations and downstream inspection. `MockOSINTTool` supplies initial source records and the second-source check. `MockRelationshipTool` supplies relationship/coverage observations. All are selected by capability through `ToolRegistry`.

EthereumInvestigationTool now implements real collection through EthereumProvider and BlockscoutEthereumProvider. MockEthereumTool remains the explicit offline fallback. Provider errors never replace live evidence with fixture data. LiveOSINTTool now implements public-source collection behind OSINTProvider; Gemini proposes reasoning and tool requests through a separate validated boundary.

## Ethereum configuration and coverage

All provider connection settings are read from environment variables; see backend/.env.example.

| Variable | Purpose / default |
| --- | --- |
| ETHEREUM_PROVIDER | blockscout |
| ETHEREUM_API_URL | Required for LIVE; example https://eth.blockscout.com/api/v2 |
| ETHEREUM_API_KEY | Optional bearer key; required by the PRO gateway |
| ETHEREUM_TIMEOUT_SECONDS | Per-request timeout, 15 seconds |
| ETHEREUM_MAX_PAGES | Per address/type/operation, 2 |
| ETHEREUM_MAX_RECORDS | Examined records per address/type/operation, 100 |
| ETHEREUM_GRAPH_LIMIT | Primary graph transaction-event limit, 40 |
| ETHEREUM_CASE_LIMIT | Persisted event limit per case, 1200 |

The primary graph selects significant events; the address inspector exposes paginated collected history, provenance and window summaries. First/latest dates and inbound/outbound counts refer to the fetched window, not lifetime activity. A separate provider transaction counter is labeled accordingly. Native transactions, internal traces and ERC-20 logs have distinct identities even when they share a transaction hash. Amounts remain exact decimals; token quantities are never treated as interchangeable monetary values.

Authentication errors, rate limits, timeouts, empty history and malformed responses are handled explicitly. Partial results are retained with warnings. Full failures pause the operation for retry, preserving prior evidence.

## Known limitations

FIXTURE mode is synthetic. LIVE mode collects provider-reported Ethereum records, not locally verified node data. Histories are bounded; ERC-721/1155, exhaustive tracing, automatic reorg reconciliation, fiat valuation and verified protocol/identity attribution are not included. Token logs can include spam; transfers alone never establish common control or economic linkage.

Planning and reasoning remain deterministic. Manually attached text is stored with provenance but not semantically interpreted. Fragility is a qualitative dependency heuristic, not a probability.

The browser drives durable operations; closing it pauses between requests, and reopening resumes. SQLite and an in-process lock target one backend process. No background worker, authentication or production deployment was added.

See [architecture](docs/architecture.md) for the domain and live adapter boundaries, and [demo case](docs/demo_case.md) for fixture and live walkthroughs.

## Live OSINT collection

After Ethereum collection, the Public sources panel can search a seed, discovered identifier, transaction hash, public entity name, domain or incident phrase. Existing saved LIVE cases can use this panel without being recreated. Fixture mode retains MockOSINTTool.

Configure backend/.env and restart the backend:

```dotenv
OSINT_PROVIDER=brave
OSINT_API_URL=https://api.search.brave.com/res/v1/web/search
OSINT_API_KEY=your_search_api_key
```

Obtain a key from the [Brave Search API dashboard](https://api-dashboard.search.brave.com/documentation/quickstart). It is separate from the Ethereum provider configuration. Do not paste keys into source code or commit backend/.env.

Optional no-key choices:

- Set OSINT_ALLOW_RSS_FALLBACK=true to permit a clearly reported Bing public RSS fallback when Brave is unavailable, or select OSINT_PROVIDER=bing_rss explicitly. RSS is a limited public feed, not a guaranteed search API; observe the provider's usage terms. In testing it sometimes returned unrelated results, which the application excluded.
- Set OSINT_PROVIDER=github for public GitHub issue/pull-request search. It can retrieve a matching pull request's first ten changed-file patches as original public evidence. It is not a replacement for general web search or authenticated code search.

No provider silently substitutes synthetic evidence in a LIVE case. Missing keys and failed searches produce a retryable action error. Previously collected blockchain evidence remains intact.

Click **Search public sources**, then open a result. The source view separates original excerpt, publisher/URL/publication date, a narrow safe statement, limitations and corroboration. **Find independent corroboration** searches for the same identifier while excluding previously collected publisher domains. Source pages are public-only; no cookies, personal accounts or private databases are used.

Provider configuration also includes timeout, bounded retries with backoff, maximum results, cache lifetime and optional page fetching; see backend/.env.example. Search and page caches are bounded in-memory TTL caches. Completed identical actions and persisted source fingerprints prevent repeated collection. Cache entries do not persist across backend restarts.

POST /investigations/{id}/search starts an OSINT action (202):

```json
{"target_id":"eth-0x...","capability":"search_exact_wallet_address"}
```

Use an existing entity/transaction ID, or replace target_id with query for a public name/domain/identifier. Capabilities include search_transaction_hash, search_entity_name, search_domain, search_public_identifier, search_incident_context, verify_external_attribution and find_independent_corroboration. The browser continues the normal advance/reanalysis loop automatically. The original /osint route still stores manually supplied text without fetching it.

Implementation files:

- services/osint_provider.py: OSINTProvider, LiveSearchProvider, public adapters, MockOSINTProvider, retries/cache.
- services/public_source.py: bounded public-page fetcher, redirect/DNS checks and HTML text extraction.
- services/osint_extraction.py: exact matching, source classification, candidate identifiers and independence heuristics.
- services/osint_tool.py: LiveOSINTTool produces observations only.
- services/osint_reasoning.py: executable searches and deterministic narrow source claims.
- models/osint.py: structured PublicSource provenance.
- frontend/src/components/PublicSources.tsx: source searches and provenance inspection.
- backend/tests/test_osint.py: mocked external APIs and safety/recovery tests.

Source mentions are not attribution. A retrieved document with an exact identifier match can support a PUBLIC-SOURCE FACT that the document mentions it. A search snippet alone supports only a qualified inference. A source saying an address belongs to an attacker does not make ownership or guilt a fact. Real-world control remains unknown.

Independence is conservative: same publishers, repeated content and shared upstream citations do not count as independent corroboration. YES means only a heuristic candidate when distinct publishers describe their own examination without detected dependence; analyst verification is still required. Publication dates are source/provider supplied. Candidate names/handles/domains are co-mentions and never merged into a person.

Known limits: bounded pages and excerpts, no JavaScript rendering or PDF extraction, no exhaustive crawling, no verified named-entity resolution, and heuristic publisher/independence classification. Some sources block fetching; search snippets remain explicitly indirect. Gemini reasoning is optional and runs only on the backend when configured.

A manual no-key GitHub validation found https://github.com/1712n/dn-institute/pull/68 from the development wallet alone. Its public patch contained the exact address and linked upstream reports. The stored statement records only that this document mentions the wallet. No incident names, report URLs or ownership conclusions are hardcoded in the live adapter. Brave transport is tested with mocked responses; a configured Brave key is needed for live Brave verification.


### No-key DuckDuckGo setup (DDGS)

The example configuration now selects `OSINT_PROVIDER=ddgs` (`duckduckgo` is also accepted). Install the updated backend requirements, restart the backend, open a LIVE case, and click **Search public sources**. No OSINT key or paid account is required. Existing keys are ignored by this provider.

The adapter explicitly selects the DuckDuckGo backend of [DDGS](https://github.com/deedy5/ddgs), retains the existing cache and bounded retries, and sends results through the same exact-match, provenance and evidence checks. It does not silently query other DDGS engines. DuckDuckGo can block automated requests; ambiguous no-result failures remain retryable errors rather than claims that public evidence does not exist. Bing RSS fallback remains specific to Brave; GitHub is separately selectable with `OSINT_PROVIDER=github`.


## Gemini planning and reasoning

Add your key to `backend/.env` (never to the frontend), then restart the backend and start a **new LIVE investigation**:

```env
GEMINI_API_KEY=your_actual_key
GEMINI_MODEL=gemini-3.6-flash
MAX_AUTO_STEPS=5
GEMINI_TIMEOUT_SECONDS=45
GEMINI_RETRIES=1
```

Gemini is enabled automatically when a key is present. `GEMINI_ENABLED=false` explicitly keeps new LIVE cases deterministic; `GEMINI_ENABLED=true` without a key produces a clear configuration error. Existing cases retain their saved reasoning mode. Fixture cases always remain offline. Keep `OSINT_PROVIDER=ddgs` for no-key public search. Gemini usage/quota is separate from OSINT and depends on your Google account/model.

The backend sends a bounded structured evidence context to Google's Gemini API: your objective, selected entities, normalized transactions, provenance and public-source excerpts, prior claims and explanations. It never sends .env configuration, credentials or full raw provider payloads. Sources are explicitly labeled untrusted. Setup: [Google AI Studio](https://aistudio.google.com/apikey). API references: [structured output](https://ai.google.dev/gemini-api/docs/structured-output), [generateContent](https://ai.google.dev/api/generate-content).

Gemini returns typed plans and capability/target requests. The backend allowlist validates them, executes the existing Ethereum/Solana/OSINT adapters, saves evidence, and asks Gemini to reevaluate after each tool. `get_case_evidence`, `get_case_entities`, `get_claims` and `get_competing_explanations` refresh the structured case context without creating evidence. No provider SDK is required; server-side HTTPX calls use JSON Schema structured output.

The workspace labels Gemini reasoning, shows the persisted automatic-step count, and offers **Pause automatic collection**. A running request may finish first. The initial run executes at most `MAX_AUTO_STEPS` tools (0-10); refreshes do not reset the budget. Model transport retries and one output-correction retry are separately bounded. Clicking a recommended action explicitly starts a new bounded run, including that action. With a zero budget, only the explicitly clicked action executes. The top deterministic candidate is used for automation; an approval/manual candidate returns control rather than silently choosing a lower-ranked action.

Execution policy is backend-owned: known-address reads and public searches are AUTO; searches/expansions of extracted candidate entities require ANALYST_APPROVAL; manual_review is MANUAL and cannot execute through the API. The backend enforces these rules independently of model wording. Analyst approval is the explicit **Approve and run** action. No separate autonomous background worker exists: the browser advances committed operations and closing it pauses progress until restore.

FACT claims must copy a backend-generated canonical statement and its evidence references exactly. Blockchain facts describe recorded successful transactions; public-source facts establish only document mentions. Other conclusions remain evidence-backed inferences, capped at MEDIUM confidence. Ownership remains explicitly unknown. Explanation support is conservatively LOW; no numerical certainty is generated. References, unsupported tools, invented URLs/hex identifiers, extra fields and invalid categories are rejected. Validation checks structure and provenance, not semantic truth of every inference: analyst review remains necessary.

The summary is composed only from accepted claim statements. **Why this assessment?**, **Why this explanation?**, and claim drawers expose concise rationales, sources, evidence IDs, contradictions, unknowns and limitations. Hidden model reasoning is never displayed or saved. Missing prior unknowns are retained; omission alone cannot resolve them.

Gemini proposes action titles, targets, purposes and explanation/claim links. Backend code assigns every numeric score: discrimination is min(9, 4 + 2 per distinct referenced explanation + up to 1 for claim linkage). Quality/ease/reliability are 9/7/8 for Ethereum, 6/8/6 for OSINT, 2/10/5 for case reads and 5/2/5 for manual review. The original 40/25/20/15 weighted formula ranks candidates. Scores are heuristics, not probabilities.

On reasoning failure the prior assessment and all collected evidence remain saved. A schema/reference failure gets one correction attempt; then the case returns an error and analyst retry control. Retrying analysis does not recollect the completed tool. Logs contain safe error categories and token counts, not keys or model output. Successful-call usage metadata is retained in the case; it is not a billing report.

New files: `backend/app/schemas/gemini.py`, `services/gemini_context.py`, `services/gemini_tools.py`, `backend/tests/test_gemini.py`, and `frontend/src/components/GeminiAssessment.tsx`. `services/gemini.py` now contains the actual client/engine. Domain/workflow metadata, orchestration, UI inspectors and browser tests were extended compatibly. Live Gemini verification requires a configured key; automated tests mock every external service. Context selection is bounded (up to 20 recent public sources plus 60 other records), with omission counts, so assessment is not exhaustive.


## Solana and mixed-chain investigations

See [Solana setup and acceptance checks](docs/solana_setup.md). LIVE mode accepts Solana addresses and mixed Ethereum/Solana seeds. **Chain scope** adds another wallet to an existing case. Parsed SOL/SPL transfers enter the existing evidence, graph, claims and action pipeline. Solana addresses remain case-sensitive.

The default public mainnet RPC requires no key. Dedicated RPC configuration is optional. Cross-chain links require a cited record and explicit analyst input; the graph labels them as uncertain inferences. No bridge attribution is inferred from matching amounts or timing.

Gemini's default is now `gemini-3.6-flash`: the configured account's API rejected the former `gemini-2.5-flash` model as unavailable. Model availability and quotas depend on the account. A 404 now points directly to model configuration; a rate-limit error never switches silently to fixture reasoning.
