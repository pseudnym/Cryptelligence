# Interactive investigation loop

MVP1 has separate fixture and LIVE Ethereum modes. Reasoning remains deterministic; no live web search, Gemini or sponsor integrations are present. The original fixture lifecycle is described below, followed by the live Ethereum extension. Creation no longer loads a completed fixture case.

## Lifecycle

POST /investigations validates 1–10 distinct Ethereum-format addresses and a required nonblank question. It saves an Investigation, seed entities and an investigation_created event. Evidence, claims, explanations and actions are initially empty; revision is 0.

The frontend requests one POST /investigations/{id}/advance operation at a time:

1. CREATED → PLANNING: the planner generates and persists a question-conditioned plan.
2. PLANNING → COLLECTING: dispatch the first plan step and record why it runs.
3. COLLECTING: each step is first marked running, then its tool executes on the following request. Returned observations are normalized and persisted. Counts and evidence IDs in the activity log come from actual output.
4. COLLECTING → ANALYZING: all plan steps completed; the evidence set is ready.
5. ANALYZING → AWAITING_ACTION: reasoning builds claims and competing explanations, the action engine identifies the important unknown and ranks next steps, and revision 1 is saved.
6. Executing a selected action first persists EXECUTING_ACTION. The next advance runs its tool, merges new evidence, logs completion and enters REANALYZING.
7. The following advance recomputes claims, explanation support, the important unknown, fragility and actions. It saves a before/after revision and returns to AWAITING_ACTION.
8. When no executable actions remain, the case enters COMPLETE. Remaining unknowns are preserved.
9. A failed operation enters ERROR with a persisted failure event and resume state. Retry restores the interrupted operation; previously committed evidence remains intact.

COMPLETE means available local collection is complete, not that the case is proven.

## Service boundaries

| Boundary | Implementation | Responsibility |
| --- | --- | --- |
| Seed provider | FixtureProvider | Map supplied seeds to available local coverage; never relabel unrelated addresses as the development seed |
| Planner | Planner protocol / DeterministicPlanner | Prioritize steps from the question |
| Collection | InvestigationTool protocol / ToolRegistry | Select exactly one tool by capability and return structured observations |
| Evidence | EvidenceService | Normalize provenance, validate references and merge idempotently |
| Reasoning | ReasoningEngine protocol / DeterministicReasoningEngine | Build fact/inference/unknown claims and competing explanations from collected evidence |
| Action engine | ActionEngine | Generate candidates, preserve completed action state and derive the important unknown |
| Scoring | scoring.py | Compute the fixed weighted score and structural fragility |
| Revisions | revisions.py | Save before/after evidence, reasoning, unknowns, recommendations and fragility |
| Orchestration | InvestigationOrchestrator | Enforce transitions, execute generic operations, persist events, revisions and errors |
| Storage | CaseRepository / SQLiteCaseRepository | Validate and persist complete case snapshots atomically |

The orchestrator contains no Ethereum or OSINT collection logic. The fixture provider reads only entities, transactions and evidence; the fixture's pre-authored claims, hypotheses and actions are not used by the new creation flow.

## Mock tools

- MockEthereumTool: activity, protocol inspection, one-hop expansion and bridge coverage checks. It returns synthetic transfers, entities and observations.
- MockOSINTTool: local attribution/service excerpts and a second-source observation. No URL is fetched.
- MockRelationshipTool: relationship coverage records and explicit no-coverage observations for additional seeds.

Tools cannot directly create Claim or Hypothesis objects. Observation and ToolResult are the collection contract; EvidenceService turns observations into Evidence.

The planner always covers the four source areas. Ownership/control questions prioritize external intelligence; bridge/protocol questions prioritize bridge inspection after activity; other questions prioritize inbound/outbound flows. Step reasons record the chosen focus.

## Domain additions

Investigation.status is the persisted state machine. seed_entities stores all seed references; seed_entity retains the primary reference for compatibility.

InvestigationPlan contains PlanStep records with adapter, capability, reason, status and produced evidence IDs.

InvestigationEvent stores a unique ID, case ID, UTC timestamp, event type, title, description, related entities/evidence and structured metadata. The ordered list is the audit sequence; timestamps are not used as unique IDs.

Claim.reasoning_category separates:
- FACT: supported observation with direct blockchain evidence in this MVP.
- INFERENCE: evidence-backed interpretation.
- UNKNOWN: an unanswered question, allowed to have no supporting evidence.

Hypothesis includes support_assessment independently of categorical confidence. A source challenge can weaken support without fabricating a new confidence probability.

MostImportantUnknown links a question and reason to required claims, related explanations and remaining resolution actions.

CaseRevision preserves added evidence IDs, changed claim/explanation snapshots, resolved/introduced/still-open questions, previous/new recommended action and before/after fragility. The snapshot permits comparison across restarts.

## Consistency and recovery

The operation version and analyst-facing revision serve different purposes. version increments on every committed operation; revision increments only when a new evidence/completed-action fingerprint is analyzed.

Advance requires expected_version. A stale duplicate request returns the current state without running another operation. An application lock serializes mutation sequences in the single-process MVP. Repeating a started/completed action is idempotent.

Evidence is deduplicated by ID or exact source/type/raw observation. Conflicting content for an existing ID is rejected. Merge validates an entire draft before publishing it. Failure rolls back the in-progress operation while preserving earlier commits, then records ERROR. Reanalysis with the same fingerprint is a no-op.

The browser drives persisted operations rather than a background job. Closing it pauses between operations; reopening the saved URL resumes from SQLite. A 400ms interval between requests makes actual committed results readable. Timers do not invent state changes, evidence, progress or events.

Old snapshots load through a compatibility validator. Their earlier operation history is not fabricated; starting a new action records the imported baseline.

## Ranking and uncertainty

total = 0.40 × discrimination + 0.25 × evidence quality + 0.20 × ease + 0.15 × source reliability

Inputs remain 0–10 scenario values, not probabilities. Completed actions are excluded; ties use action ID. Scores stay inside a UI disclosure.

Fragility counts weak/single-source supporting statements, attribution dependencies and shared claim relationships. It is structural, not statistical. Distinct source identifiers do not establish independence.

The important unknown prioritizes unknown claims required by the most explanations. No-coverage cases do not force explanations or invent three meaningless actions.

## Frontend

The existing workstation layout is preserved. Setup supports multiple addresses and a required question. InvestigationActivity renders the plan and persisted event history. Evidence/graph counts grow while collection runs. Claim rows and the Statements tab distinguish facts, inferences and unknowns.

The assessment and explanation reasoning come from the backend. RevisionSummary displays new evidence, changes in support, resolved and remaining questions, and the new next step. Errors expose retry without resetting the case.

## Future replacements

- LIVE Ethereum collection is implemented through EthereumInvestigationTool and BlockscoutEthereumProvider; MockEthereumTool remains the explicit offline fallback.
- LiveOSINTTool now collects public sources through Brave, optional Bing RSS, or public GitHub; MockOSINTTool remains exclusive to fixtures.
- GeminiEngine implements optional LIVE planning and reasoning with strict proposals; deterministic planners remain the offline path.
- Replace candidate generation in ActionEngine when needed; retain deterministic score calculation.
- Replace SQLiteCaseRepository with transactional Postgres storage and optimistic concurrency before using multiple server workers.

Storage replacement remains a future boundary. Real Ethereum is implemented as described below.

## Tests

Backend tests cover the staged lifecycle, meaningful action updates, model/reference validation, exact amounts, scoring, unknown coverage, question-specific plans, stale/duplicate requests, failed collection/action retry, atomic deduplication, no-op reanalysis, OSINT provenance and mid-collection restart recovery.

Playwright uses fresh servers on 8010/5174, isolated from normal development ports. Tests watch actual intermediate responses, evidence growth, revision changes and recommendations, plus existing inspection, keyboard/copy, responsive and error behaviors.

## Live Ethereum collection and pivots

The setup screen persists an explicit LIVE or FIXTURE choice. LIVE seeds use address-derived IDs and never use FixtureProvider. Collection failures never fall back to synthetic records inside a live case. Selecting FIXTURE starts an independent offline demonstration.

### Provider boundary

EthereumProvider exposes address inspection, transaction counters, bounded history by record kind/direction and transaction inspection. BlockscoutEthereumProvider implements the transport; MockEthereumProvider supplies normalized offline test data. Existing MockEthereumTool remains the fixture demonstration.

Blockscout v2 field normalization is confined to blockscout.py. The application receives Entity and TransactionEvent objects, not vendor JSON. API URL, optional bearer key, provider selection, timeouts, page/record limits, graph limit and case limit come from environment variables. The key is never returned to the frontend or persisted in evidence.

Normalization preserves exact Decimal quantities and distinguishes native transactions, ERC-20 logs and internal trace indexes. A parent transaction hash is not a unique event ID: multiple logs and internal transfers can share it. Confirmed failure/unknown execution is retained in history but excluded from successful transfer claims and graph selection. Contract addresses are recognized from provider flags; provider names/tags are not promoted to identity or protocol attribution.

### Evidence and summarization

Each normalized event creates immutable provenance-aware blockchain evidence with chain, hash, block, timestamp, sender/receiver IDs, asset, exact amount, record type, provider, source URL and collection timestamp. Receipt evidence separately records coverage, examined counts, warnings, limits and scope.

A case stores bounded normalized history. Summaries report distinct parent transaction counts separately from event counts; inbound/outbound, token/internal counts, counterparties, largest flows, sampled first/latest timestamps and contract interactions refer to the collected window. A provider lifetime transaction counter is labeled separately. Native and internal values are never combined into a total; token assets include their contract address to avoid symbol collisions.

Normal history is requested in descending native-value order; token/internal endpoints use provider pagination. The first/latest observations are therefore not claimed to be lifetime endpoints. Significant records are selected within each asset and record kind, round-robin across groups. High-value flags mean greater than ten times the positive median within the same asset/type, not suspiciousness or fiat value.

The primary graph renders at most ETHEREUM_GRAPH_LIMIT transaction events plus their endpoints and supplied seeds. New collection windows take priority. Cyclic live graphs use a force layout and approximate compact display amounts; inspectors preserve exact quantities and full token contract identifiers. Previously collected events remain available through paginated address detail views and GET /investigations/{id}/entities/{entity_id}/history. This endpoint's pagination is local history pagination, not a request for unlimited provider pages.

### Execution and reasoning

The live plan collects native, internal and ERC-20 records. Token questions prioritize token collection. Public-source searches run as explicit live investigative actions; fixture source checks never run in live mode.

Wallet/contract drawers expose Expand inbound, Expand outbound and Inspect counterparty. POST /investigations/{id}/expand accepts entity_id and direction (inbound, outbound, inspect); it creates a targeted investigative action and starts the existing EXECUTING_ACTION → REANALYZING loop. The tool fetches the selected address, evidence merges into the same case, claims are rebuilt and a revision records changes. Completed identical pivots are idempotent.

EthereumInvestigationTool also supports inspect_address, get_transactions, get_token_transfers, get_internal_transactions, inspect_transaction, identify_top_counterparties, identify_contract_interactions and expand_counterparty capabilities. The transaction-inspection provider method is a point lookup; UI history inspection normally reads already-persisted evidence.

Live reasoning is deterministic and separate from fixture rules. Successful significant records create sourced facts. When receipts and outbound flows exist, related onward payments and independent activity are alternative explanations with low support. Neither establishes economic linkage or common ownership. Ownership and coverage unknowns remain explicit. Candidate actions prioritize discovered outbound branches and source-of-funds/counterparty inspection. New evidence changes claims, coverage, revision and next action without fabricating attribution.

### Errors, recovery and bounds

Authentication, rate limiting, timeouts, invalid inputs, malformed responses and unavailable endpoints produce sanitized errors. Entirely failed operations enter ERROR and can retry. Successful pages from a partially failed history request, successful history types in a pivot, and successful seeds in a mixed collection are retained with warning events. Earlier persisted evidence is never discarded.

Malformed rows are excluded with warnings. Empty history produces a coverage receipt and unknowns, not an inactivity or innocence conclusion. Provider reindexing that conflicts with an immutable stored event pauses collection; automatic reorg reconciliation is not implemented.

Defaults: two pages / 100 examined records per type per address per operation, 40 primary-graph events and 1,200 total persisted events per case. These are bounded local investigations, not exhaustive tracing. Reaching the case limit requires a new case or a deliberate configuration change; history is not silently evicted.

### Validation and remaining scope

Automated unit and browser tests require no external API. Playwright starts backend/tests/browser_app.py, which injects a synthetic offline provider only for tests. Production app.main never imports this test server. The normal fixture flow is tested against the same lifecycle.

A separate manual real-provider check on the development seed collected 206 events (100 native, 100 ERC-20, 6 internal), with a provider transaction counter of 228. The first recommended outbound pivot added 101 evidence objects and 27 entities in the same case, reached revision 2 and changed the recommendation. These are observations from this validation run, not fixed acceptance constants or hardcoded expected results.

No Solana or sponsor integration was added. ERC-721/1155, unlimited history, fiat valuation, token legitimacy, protocol identification, finality/reorg monitoring and identity attribution remain outside this pass.

Provider reference: [Blockscout address API](https://github.com/blockscout/agent-skills/blob/main/blockscout-analysis/references/blockscout-api/addresses.md), [Blockscout PRO authentication](https://github.com/blockscout/agent-skills/blob/main/web3-dev/SKILL.md). Public-instance availability and limits may differ from the authenticated PRO gateway.


## Live public-source collection

POST /investigations/{id}/search creates a targeted action and uses the existing execution, evidence merge and reanalysis lifecycle. The case ID stays stable. Search failures preserve existing evidence and support retry. Empty or irrelevant results create a coverage receipt, never a claim that no public information exists.

LiveOSINTTool depends on OSINTProvider. LiveSearchProvider implements Brave (default), explicit optional Bing RSS fallback and optional public GitHub issue/PR search. OSINTSettings centralizes configuration; API credentials remain server-only. Exact quoted identifiers are searched without development-case-specific logic. Bounded retries, exponential backoff and process-local TTL caching control requests.

PublicPageFetcher fetches bounded public HTML/text with DNS-address validation, pinned connections, redirect validation and no scripts, cookies or authentication. Search snippets remain distinguishable from retrieved originals. Provider and page text are untrusted data, never executable instructions. GitHub PR patches are bounded to the first ten changed files.

PublicSource stores publisher, URL through Evidence, collection/publication dates, excerpt, exact-match status, identifiers, citations and independence assessment. Evidence is deduplicated by canonical URL and content fingerprint. Candidate identifiers represent co-mentions and never establish identity or common control. The source UI separates provenance, source statements, safe conclusions, limitations and corroboration.

Public-source FACT claims can only state that the retrieved document mentions the identifier, and must exactly match its stored narrow statement. Search snippets support qualified inferences. Ownership remains unknown. Shared publishers, copied wording and common citations conservatively defeat independence; distinct research markers can suggest candidate independence but require analyst verification. Gemini may synthesize evidence but cannot create source truth or verified attribution.


## Gemini boundary and bounded loop

GeminiSettings, GeminiClient and GeminiEngine live in services/gemini.py. Structured response schemas live in schemas/gemini.py; gemini_tools.py owns capability definitions, target validation, execution policy and score components; gemini_context.py owns bounded context and canonical FACT statements. All network calls occur server-side, with a fixed Google endpoint and key header. No SDK-side automatic tool execution is enabled.

A case persists reasoning_mode, auto_steps, max_auto_steps, automation_paused, usage metadata and summary claim IDs. Old JSON cases receive safe defaults. New LIVE cases select Gemini when configured. A Gemini plan creates typed steps and targeted actions. The first allowed step collects evidence; every subsequent analysis validates a fresh assessment, records a revision, and ranks candidates using backend scores. The top AUTO action runs only if budget remains. Every action start increments the persisted counter. Pending plan actions remain reviewable, while revised candidates replace matching defaults.

Successful collection is committed before analysis. Failed reasoning rolls back the draft assessment, preserves evidence and completed actions, and enters a retryable ERROR. Transport attempts and correction attempts are bounded. Existing optimistic version checks and repository locks prevent repeated browser advances from duplicating operations. Explicit action execution starts another bounded run; pause stops subsequent automatic actions. MANUAL actions reject execution, and ANALYST_APPROVAL candidates never auto-start.

Gemini receives allowlisted tool definitions and returns structured requests; the backend is the only executor. Case-read capabilities refresh already-bounded context and never manufacture observations. Plan and action targets must already exist. Transaction inspection materializes an entity only from an existing transaction hash. Candidate co-mentions require analyst approval. No arbitrary URLs, shells, database queries or new external integrations are exposed.

Reasoning validation rejects unknown references, unsupported FACT text, unknowns labeled as resolved, invented URLs and blockchain identifiers, unsupported tools, numeric certainty and schema extras. FACT text must match backend canonical observations exactly. Inference meaning still requires human review; reference validation is not proof of entailment. Prior unknowns cannot disappear merely because a later model response omits them. Summary text comes exclusively from validated claim statements. Hypotheses and actions retain evidence-linked rationales and limitations for UI inspection, not chain-of-thought.

The context excludes raw provider metadata and configuration, caps public excerpts and selected records, and labels source content untrusted. Its limits are explicit to the model. Token counts are logged when available, while source text, response bodies, secrets and hidden thought parts are not logged. See README for configuration, limits and deterministic score policy.


## Solana and chain scope

A Case contains Ethereum and Solana entities, transfers, evidence and optional CrossChainRelationship records. Solana base58 identifiers preserve case; Ethereum addresses normalize to lowercase. POST /seeds adds and collects a wallet within an existing settled case. No separate per-chain workspace exists.

Solana JSON-RPC -> SolanaRPCProvider normalization -> SolanaInvestigationTool -> EvidenceService -> saved case -> deterministic/Gemini assessment -> graph and analyst action. The provider alone reads raw RPC; the reasoning context receives normalized records. Signature + outer/inner instruction position identifies each event. Failed execution, unavailable timestamps and undecodable movement do not become transfer facts. Program interactions remain execution evidence with program IDs, without guessed protocol names.

An explicit analyst proposal cites existing case evidence and creates a traceable analyst-input observation. Its cross-chain edge is permanently categorized INFERENCE. Similar values/times cannot create links automatically. All evidence references and endpoint chains are validated before saving, then ordinary reanalysis runs. Existing stored cases default to an empty relationship list.
