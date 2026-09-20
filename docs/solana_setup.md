# Solana investigation setup

Start the backend and frontend using README.md. No Solana package or API key is required: HTTPX calls the configured HTTPS JSON-RPC endpoint. Restart the backend after changing settings. Use a new LIVE case to apply Gemini reasoning settings.

```env
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_CLUSTER=mainnet-beta
SOLANA_TIMEOUT_SECONDS=15
SOLANA_RETRIES=1
SOLANA_MAX_SIGNATURES=10
SOLANA_CASE_LIMIT=1200
GEMINI_MODEL=gemini-3.6-flash
```

Set GEMINI_API_KEY privately in backend/.env for Gemini. GEMINI_ENABLED=false explicitly selects deterministic reasoning for new LIVE cases; this does not demonstrate Gemini acceptance. The public RPC is rate limited. A dedicated RPC URL can contain private access credentials; it is never included in evidence, browser responses, or reasoning context. Keep the configured cluster stable for persisted cases. The endpoint must serve the configured cluster; mainnet-beta is the development/demo target.

## Demonstration

1. Select LIVE. Enter `CxegPrfn2ge5dNiQberUrQJkHCcimeR4VXkeawcFBBka` and ask: "What recorded Solana activity can we establish, where did funds go, and what remains uncertain?"
2. Start investigation. Actual provider records become provenance-aware evidence. No attribution is hardcoded.
3. Select a transfer or counterparty with **Inspect graph record**. Open its evidence to inspect signature, slot, timestamp, instruction index, collection details and public Solana Explorer source URL.
4. Select a counterparty and **Expand outbound** or **Inspect counterparty**. Evidence and assessment update in the same case.
5. Open **Chain scope > Add a wallet to this investigation**. Enter Ethereum development seed `0x629e7Da20197a5429d30da36E77d06CdF796b71A` and **Collect added wallet**. The same graph now displays both chains.
6. For a justified analyst proposal, open **Propose an evidence-backed cross-chain link**, choose both entities and existing evidence, and state the proposed relationship and limitations. **Record proposed link** creates cited analyst evidence and a dashed INFERENCE edge. It does not verify common control or a bridge match.
7. Reload: evidence, graph, proposals and revisions persist. With Gemini configured and quota available, its plan and assessment use the same validated Solana capabilities.

## API and implementation

- POST `/investigations`: `mode=live`, one to ten Ethereum/Solana seeds, question.
- POST `/investigations/{id}/seeds`: `{"address":"..."}` collects into an existing settled LIVE case.
- POST `/investigations/{id}/expand`: existing entity ID and direction `inbound`, `outbound`, or `inspect`.
- POST `/investigations/{id}/relationships`: source_entity_id, target_entity_id, evidence_ids, statement. Requires different supported chains and real case references.
- Continue operations using the normal version-checked `/advance` endpoint; the frontend does this automatically.

`chains.py` provides case-sensitive base58 validation and chain-neutral entity/fact helpers. `solana_provider.py` owns JSON-RPC and normalization. `solana_tool.py` implements all eight Solana capabilities in the existing InvestigationTool contract. Gemini uses existing IDs, never arbitrary endpoints. `ChainScope.tsx` provides same-case addition and cited analyst proposals.

Legacy and v0 transactions use jsonParsed encoding. Each outer/inner instruction has a stable event ID so repeated transfers in one signature remain distinct. Parsed System SOL and SPL Token/Token-2022 transfer instructions preserve exact decimal amounts. RPC-reported token owners map token accounts to addresses; this does not identify real-world controllers. Execution/program records preserve program IDs, slot, status, fee and bounded balance deltas. Unknown programs are not assigned guessed protocol labels. Failed transactions and missing timestamps never create invented transfer events. Balance deltas are context, not inferred transfers.

## Limits and checks

Collection reads a bounded latest-signature window without archival pagination. Not all instructions, swaps, confidential transfers, historical token accounts or bridge protocols can be decoded. Successful execution with no recognized transfer is still evidence, not proof of inactivity. Unavailable history, malformed records, rate limits and timeouts are explicit. Partial successful collection retains evidence and warnings. Graph rendering uses bounded significant transfers. Fixture mode remains the original Ethereum-only offline case.

Automated tests use synthetic RPC responses, never live network or real attribution. They cover validation, legacy/v0 parsing, SOL/SPL amounts, evidence, deduplication, mixed chains, graph expansion, provider failures, Gemini tool selection, analyst links and browser persistence. Run the backend and browser commands in README.md.

Live validation collected mainnet activity from the development Solana seed and real Ethereum records in one case. This alone does not verify Gemini, ANS, Tiger Data, or Vultr. The hackathon's sequential acceptance gates remain in force; do not label the overall MVP complete until each live integration passes.


## Current acceptance checkpoint (2026-09-20)

PASS: real mainnet seed collection, public provenance, real counterparty expansion (revision 2), real Ethereum/Solana observations in the same in-memory case, automated Gemini capability validation/reanalysis, and browser persistence/analyst-link flow.

BLOCKED: full live Gemini plan -> Solana collection -> assessment. Google returned 404 for gemini-2.5-flash, so configuration and default were updated to gemini-3.6-flash. A subsequent diagnostic plan succeeded, but full-loop attempts returned HTTP 429 after bounded retries. A usable key is loaded; it is not a missing-key failure. Check the project's model quota/rate limits and retry later. No claim of live Gemini acceptance is made.

The user's Phase 1 acceptance gate therefore remains open. ANS, Tiger Data, and Vultr phases have not begun; their acceptance is not demonstrated. No live sponsor registration, database, monitoring or deployment was simulated. Complete the Gemini acceptance check before progressing to Phase 2.
