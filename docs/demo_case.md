# Watching the mock investigation

All activity is synthetic. The supplied development address is:
0x629e7Da20197a5429d30da36E77d06CdF796b71A

No real attribution or transaction verification occurs. The fixture uses fixture: identifiers instead of fabricated real hashes or source URLs.

1. Enter one or more Ethereum-format addresses and an investigation question. The default asks what activity the wallet is associated with and where funds came from/went.
2. Click Start investigation. The case initially contains only the submitted seeds and question.
3. Watch the plan appear, then its steps run. For the default question, evidence counts grow 0 → 2 → 3 → 4 → 6 as activity, relationship coverage, bridge activity and external notes are collected.
4. The evidence service normalizes each tool result. No claims are loaded from the fixture.
5. Analysis creates eight statements, including a transfer fact, attribution/control inferences and explicit ownership, identity, destination and bridge unknowns. Two competing explanations are generated.
6. Revision 1 recommends an independent source check (8.25), ahead of one-hop expansion (7.75) and bridge inspection (6.55). Scores remain secondary.
7. Run source check. EXECUTING_ACTION becomes REANALYZING after the new observation is persisted. The evidence count reaches seven before the new reasoning appears.
8. Revision 2 marks the incident attribution disputed and changes common-control support from LOW to INSUFFICIENT. The source did not provide ownership proof. The recommendation changes to following Counterparty B's next transfer.
9. Expand the flow: one 1,200 ETH synthetic B → pool transfer is added. The destination question becomes a sourced fact, while common control and real identity remain unknown.
10. Check the bridge: record the absence of a matching destination. Available actions are complete; the investigation does not claim every question was answered.
11. Refresh at any point. The case and completed operations persist; interrupted collection resumes without duplicating evidence.

An additional address with no local coverage produces an explicit coverage record and an unknown. It is never assigned the Wormhole seed's activity. A case with no supported observations finishes with insufficient evidence rather than fabricated explanations.

A failed tool pauses the case with a retry control. The UI's full activity disclosure retains the completed operations, failure and retry. Revision history preserves the exact reasoning changes after new evidence.

Canonical source observations: tests/fixtures/wormhole_mock.json. The backend mirror is tested for equality. Legacy conclusions in that fixture remain test/reference material; the active loop does not load them.

## LIVE Ethereum walkthrough

1. Copy backend/.env.example to backend/.env, merging rather than overwriting any existing settings. Restart the backend. The example selects the public Ethereum Blockscout API; no key was needed for the validation run.
2. Select LIVE DATA. Enter the development seed above, or any valid Ethereum address, and an investigation question.
3. Watch native, internal and ERC-20 collection execute. The activity log reports actual examined records and retained observations.
4. Select an address in the graph. Inspect window counts, the separate provider transaction counter, top counterparties, large transfers, coverage warnings and normalized history. Use Inspect record evidence for the exact event and provenance.
5. Choose Expand inbound, Expand outbound or Inspect counterparty. The URL/case ID stays the same. New events and entities merge into the case without duplicate hashes/log indexes.
6. Watch reanalysis and the next revision. Ownership remains unknown; recommendations follow actual discovered counterparties.
7. Switch back to FIXTURE DATA from New investigation for the deterministic offline demo. A live provider error never substitutes fixture records in an existing live case.

The real-provider validation run retained 206 events initially. The first recommended outbound pivot added 101 evidence objects and 27 entities, reached revision 2 and recommended a different address. Provider history changes; these are recorded results, not hardcoded targets.

Limits are visible: graph significance is sampled from bounded collection windows, token amounts are not fiat values, internal/native values are not added together, and no attribution or Wormhole-specific conclusion is injected.


## Live public-source walkthrough

1. Set OSINT_PROVIDER=brave and OSINT_API_KEY in backend/.env, then restart the backend. OSINT_ALLOW_RSS_FALLBACK=true optionally enables public Bing RSS; it may return irrelevant results. Never share the key in the browser or case notes.
2. Open a settled LIVE case and click Search public sources, or search the selected graph identifier. Names, domains, incidents and transaction hashes can also be submitted in the public-search disclosure.
3. Watch the action finish and the revision increase within the same case. Open a source to inspect the excerpt, publisher, date, safe conclusion and limitations. A snippet is clearly weaker than a retrieved document.
4. Inspect Statements: a public-source fact only establishes that the document mentions the target. Identity and ownership stay unknown. Candidate co-mentioned identifiers are leads requiring verification.
5. Run Find independent corroboration. Repeated URLs are deduplicated; copied reports and shared citations do not become independent confirmation. Missing credentials or provider failures show a retryable error and preserve the case.

A separate real public GitHub search for the development address found https://github.com/1712n/dn-institute/pull/68 and retrieved a patch containing the exact address. This was discovered through generic search, not a built-in Wormhole mapping. Brave transport is covered with mocked responses; live Brave requires a configured key. All automated tests use mocked external APIs.

The combined live validation collected 206 Ethereum events, then one GitHub source in the same in-memory case. Reanalysis reached revision 2, created one narrow public-source fact, preserved the identity unknown and recommended find_independent_corroboration. These counts describe a validation run and are not application constants.


## Gemini investigation walkthrough

Configure GEMINI_API_KEY and GEMINI_MODEL on the backend, restart, and start a new LIVE case with the development seed and question: "What activity is this wallet associated with, where did the funds come from, where did they go, and what remains uncertain?"

Watch Gemini's plan, targeted Ethereum/public-source collections and per-tool assessment revisions. Automatic work stops at MAX_AUTO_STEPS (default 5), an approval/manual action, or a failure. Open Why this assessment and the linked claims to inspect exact records and limitations. The most important unknown lists the affected explanations and evidence that could resolve it. Execute a recommended action to start another bounded run and inspect the next revision. Pause prevents further automatic collection after the current request completes.

Automated Gemini validation uses mocked responses and offline Ethereum/OSINT providers. The browser scenario collects chain and source evidence, stops at two steps, exposes claim explanations, then runs an analyst-selected downstream action and persists revision 3. No live Gemini result is claimed without an actual configured API key. Live Ethereum and DDGS were separately validated in earlier milestones.
