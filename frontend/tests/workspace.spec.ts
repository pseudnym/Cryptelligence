import { expect, test, type Page } from '@playwright/test';

async function start(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Start investigation' }).click();
  await expect(page.getByRole('heading', { name: 'Ready for your next step' })).toBeVisible();
}
test('create, inspect provenance, execute all actions, and reload persisted case', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await start(page);
  await expect(page.getByRole('img', { name: 'Transaction graph with 7 nodes and 6 directed links' })).toBeVisible();
  await expect(page.locator('canvas').first()).toBeVisible();
  await page.getByRole('button', { name: /The seed sent funds to Counterparty B/ }).first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('dialog').getByText('fixture:tx-out', { exact: true })).toBeVisible();
  await expect(page.getByRole('dialog').getByRole('heading', { name: 'Limitations' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('tab', { name: 'Gaps & contradictions' }).click();
  await expect(page.getByRole('heading', { name: 'Contradictions', exact: true })).toBeVisible();
  await page.getByTestId('next-step').click();
  await expect(page.getByRole('status')).toContainText('revision 2');
  await expect(page.getByRole('heading', { name: 'Follow Counterparty B’s next transfer' })).toBeVisible();
  await expect(page.locator('.briefing-assessment')).toContainText('attribution is now disputed');
  await page.getByTestId('next-step').click();
  await expect(page.getByRole('img', { name: 'Transaction graph with 8 nodes and 8 directed links' })).toBeVisible();
  await page.getByTestId('next-step').click();
  await expect(page.getByRole('heading', { name: 'Mock actions complete' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Mock actions complete' })).toBeVisible();
  await expect(page.locator('.briefing-assessment')).toContainText('Common control remains unproven');
  expect(errors).toEqual([]);
});

test('uncovered seeds return honest unknowns and backend failures are recoverable', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Ethereum wallet').fill('0x' + 'a'.repeat(40));
  await page.getByRole('button', { name: 'Start investigation' }).click();
  await expect(page.getByRole('heading', { name: 'Insufficient evidence', exact: true })).toBeVisible();
  await expect(page.locator('.briefing-assessment')).toContainText('without enough transaction');
  await page.getByRole('button', { name: 'New investigation' }).click();
  await page.getByLabel('Ethereum wallet').fill('0x629e7Da20197a5429d30da36E77d06CdF796b71A');
  await page.route('**/api/investigations', route => route.fulfill({ status: 503, body: 'unavailable' }));
  await page.getByRole('button', { name: 'Start investigation' }).click();
  await expect(page.getByRole('alert')).toContainText('Unable to load');
});

for (const width of [1440, 1920, 390]) {
  test(`workstation alignment and natural document scrolling at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1100 });
    await start(page);
    await expect(page.getByTestId('next-step')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const scrolling = await page.locator('.analysis-content').evaluate(el => ({ overflow: getComputedStyle(el).overflowY, height: el.clientHeight, scroll: el.scrollHeight }));
    expect(scrolling.overflow).toBe('visible');
    expect(scrolling.scroll).toBeLessThanOrEqual(scrolling.height + 1);
    if (width > 1150) {
      const panels = await page.locator('.work-grid > .panel').evaluateAll(els => els.map(el => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom }; }));
      expect(Math.abs(panels[0].top - panels[1].top)).toBeLessThan(1);
      expect(Math.abs(panels[0].bottom - panels[1].bottom)).toBeLessThan(1);
      const decisions = await page.locator('.decision-grid > .panel').evaluateAll(els => els.map(el => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom }; }));
      for (const panel of decisions) {
        expect(Math.abs(panel.top - decisions[0].top)).toBeLessThan(1);
        expect(Math.abs(panel.bottom - decisions[0].bottom)).toBeLessThan(1);
      }
    }
    await page.screenshot({ path: `test-results/redesign-${width}.png`, fullPage: true });
  });
}

test('entity inspector connects transactions, evidence and claims', async ({ page }) => {
  await start(page);
  await page.getByLabel('Inspect graph record').selectOption('counterparty');
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByRole('heading', { name: 'Why this entity matters' })).toBeVisible();
  await expect(drawer.getByRole('heading', { name: 'Related transactions' })).toBeVisible();
  await expect(drawer.getByRole('heading', { name: 'Linked evidence' })).toBeVisible();
  await expect(drawer.getByRole('heading', { name: 'Claims involving this entity' })).toBeVisible();
  await drawer.getByRole('button', { name: /The seed sent funds to Counterparty B/ }).click();
  await expect(page.getByRole('dialog').getByRole('heading', { name: 'The seed transferred fixture funds to counterparty B.' })).toBeVisible();
  await page.getByRole('button', { name: 'Close inspector' }).click();
  await page.getByRole('button', { name: /Seed wallet.*Liquidity pool/ }).click();
  await expect(page.getByRole('dialog').getByText('fixture:tx-pool', { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: 'test-results/entity-inspector.png', fullPage: false });
});

test('scoring is secondary, copying works and tab navigation is accessible', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await start(page);
  await expect(page.getByText('8.25/10', { exact: true }).first()).not.toBeVisible();
  await page.getByText('Why was this recommended?', { exact: true }).click();
  await expect(page.getByText('8.25/10', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Hypothesis discrimination', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Copy seed wallet address' }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('0x629e7Da20197a5429d30da36E77d06CdF796b71A');
  await page.getByRole('tab', { name: 'Explanations' }).focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: /Evidence/ })).toBeFocused();
  await expect(page.getByRole('tab', { name: /Evidence/ })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByText('Deterministic blockchain').first()).toBeVisible();
});

test('pending actions keep their layout and cannot be submitted twice', async ({ page }) => {
  await start(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/actions/a-verify/execute', async route => { await gate; await route.continue(); });
  await page.getByTestId('next-step').click();
  await expect(page.getByTestId('next-step')).toBeDisabled();
  await expect(page.getByTestId('next-step')).toContainText('Running simulated step');
  release();
  await expect(page.getByRole('status')).toContainText('revision 2');
});

test('saved-case restoration shows its loading state without flashing setup', async ({ page }) => {
  await start(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/investigations/*', async route => { await gate; await route.continue(); });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Restoring investigation' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start investigation' })).toHaveCount(0);
  release();
  await expect(page.getByRole('heading', { name: 'Ready for your next step' })).toBeVisible();
});

test('watch collection and action reanalysis produce real evidence and new recommendations', async ({ page }) => {
  let releaseCollection!: () => void;
  const collectionGate = new Promise<void>(resolve => { releaseCollection = resolve; });
  let releaseReanalysis!: () => void;
  const analysisGate = new Promise<void>(resolve => { releaseReanalysis = resolve; });
  let reanalysisVersion: number | null = null;
  const statuses: string[] = [];
  page.on('response', async response => {
    if (response.url().includes('/api/investigations') && response.request().method() === 'POST' && response.ok()) {
      const state = await response.json();
      if (state.investigation) statuses.push(state.investigation.status);
      if (state.investigation?.status === 'REANALYZING') reanalysisVersion = state.version;
    }
  });
  await page.route('**/advance', async route => {
    const version = route.request().postDataJSON().expected_version;
    if (version === 4) await collectionGate;
    if (version === reanalysisVersion) await analysisGate;
    await route.continue();
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Start investigation' }).click();
  await expect(page.getByRole('heading', { name: 'Collecting evidence' })).toBeVisible();
  await expect(page.getByLabel('Investigation plan')).toBeVisible();
  await expect(page.getByText('2 evidence records · 0 statements', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/loop-collecting.png', fullPage: true });
  releaseCollection();
  await expect(page.getByRole('heading', { name: 'Ready for your next step' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Evidence (6)' })).toBeVisible();
  await page.getByRole('tab', { name: 'Statements' }).click();
  await expect(page.getByRole('heading', { name: 'Facts in the collected records' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Inferences to test' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Unknowns', exact: true })).toBeVisible();
  await page.getByTestId('next-step').click();
  await expect(page.getByRole('heading', { name: 'Reevaluating the case' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Evidence (7)' })).toBeVisible();
  await expect(page.getByText('Revision 1', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/loop-reanalyzing.png', fullPage: true });
  releaseReanalysis();
  await expect(page.getByRole('status', { name: 'Investigation updated' })).toContainText('revision 2');
  await expect(page.getByRole('status', { name: 'Investigation updated' })).toContainText('low → insufficient support');
  await expect(page.getByRole('heading', { name: 'Follow Counterparty B’s next transfer' })).toBeVisible();
  await page.getByRole('tab', { name: 'Explanations' }).click();
  await expect(page.getByText('Support: insufficient', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/loop-updated.png', fullPage: true });
  expect(statuses).toEqual(expect.arrayContaining(['CREATED', 'PLANNING', 'COLLECTING', 'ANALYZING', 'AWAITING_ACTION', 'EXECUTING_ACTION', 'REANALYZING']));
});

test('multiple seeds and a control question affect the persisted plan', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '+ Add wallet' }).click();
  await page.getByLabel('Ethereum wallet 2', { exact: true }).fill('0x' + 'b'.repeat(40));
  await page.getByLabel('Investigation question').fill('Who controls these wallets?');
  await page.getByRole('button', { name: 'Start investigation' }).click();
  await expect(page.getByRole('heading', { name: 'Ready for your next step' })).toBeVisible();
  await expect(page.locator('.case-identity .address')).toHaveCount(2);
  await expect(page.locator('.plan-step').first()).toContainText('Check external intelligence');
  await expect(page.getByRole('tab', { name: 'Evidence (7)' })).toBeVisible();
});

test('reload during collection resumes the saved operation without duplicate evidence', async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/advance', async route => {
    if (route.request().postDataJSON().expected_version === 4) await gate;
    await route.continue();
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Start investigation' }).click();
  await expect(page.getByText('2 evidence records · 0 statements', { exact: true })).toBeVisible();
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  release();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Ready for your next step' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Evidence (6)' })).toBeVisible();
  await expect(page.getByText('Revision 1', { exact: true })).toBeVisible();
});

test('LIVE Ethereum collection and graph pivot update the same case with offline provider responses', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Data mode').selectOption('live');
  await page.getByLabel('Ethereum or Solana wallet 1', { exact: true }).fill('0x' + 'a'.repeat(40));
  await page.getByRole('button', { name: 'Start investigation' }).click();
  await expect(page.getByRole('heading', { name: 'Ready for your next step' })).toBeVisible();
  await expect(page.locator('.workspace .environment-banner strong')).toHaveText('LIVE DATA');
  await expect(page.locator('.briefing-assessment')).toContainText('normalized blockchain events');
  const originalUrl = page.url();
  await page.getByLabel('Inspect graph record').selectOption('eth-0x' + 'b'.repeat(40));
  await expect(page.getByRole('dialog').getByRole('button', { name: 'Expand outbound' })).toBeVisible();
  await expect(page.getByRole('dialog')).toContainText('Collected history');
  await page.getByRole('dialog').getByRole('button', { name: 'Expand outbound' }).click();
  await expect(page.getByRole('status', { name: 'Investigation updated' })).toContainText('revision 2');
  expect(page.url()).toBe(originalUrl);
  await expect(page.locator('.briefing-assessment')).toContainText('4 normalized blockchain events');
  await expect(page.getByRole('heading', { name: /Trace outbound activity from 0xcccccc/ })).toBeVisible();
  await page.getByLabel('Inspect graph record').selectOption('eth-0x' + 'b'.repeat(40));
  await expect(page.getByRole('dialog')).toContainText('Collected window: outbound');
  await page.getByRole('dialog').getByRole('button', { name: 'Inspect record evidence' }).last().click();
  await expect(page.getByRole('dialog').getByText('Source details & raw record')).toBeVisible();
  await page.getByRole('dialog').getByText('Source details & raw record').click();
  await expect(page.getByRole('dialog').locator('pre').last()).toContainText('"source_provider": "offline_test_provider"');
  await page.getByRole('button', { name: 'Close inspector' }).click();
  await page.screenshot({ path: 'test-results/live-pivot.png', fullPage: true });
  await page.reload();
  await expect(page.locator('.workspace .environment-banner strong')).toHaveText('LIVE DATA');
  await expect(page.getByRole('status', { name: 'Investigation updated' })).toContainText('revision 2');
});

test('public-source search adds provenance and narrow claims while keeping identity unknown', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Data mode').selectOption('live');
  await page.getByLabel('Ethereum or Solana wallet 1', { exact: true }).fill('0x' + 'a'.repeat(40));
  await page.getByRole('button', { name: 'Start investigation' }).click();
  await expect(page.getByRole('heading', { name: 'Ready for your next step' })).toBeVisible();
  const originalUrl = page.url();
  const panel = page.getByLabel('Public-source investigation', { exact: true });
  await panel.getByRole('button', { name: 'Search public sources', exact: true }).click();
  await expect(page.getByRole('status', { name: 'Investigation updated' })).toContainText('revision 2');
  expect(page.url()).toBe(originalUrl);
  await expect(page.locator('.briefing-assessment')).toContainText('public-source records');
  await expect(page.locator('.next-step-title')).toContainText('Find independent public references');
  await panel.locator('.source-result').first().click();
  const drawer = page.getByRole('dialog');
  for (const name of ['SOURCE', 'WHAT THE SOURCE SAYS', 'WHAT WE CAN SAFELY CONCLUDE', 'LIMITATIONS', 'CORROBORATION']) {
    await expect(drawer.getByRole('heading', { name, exact: true })).toBeVisible();
  }
  await expect(drawer).toContainText('research.example');
  await expect(drawer).toContainText('does not establish ownership');
  await page.screenshot({ path: 'test-results/osint-source.png' });
  await page.getByRole('button', { name: 'Close inspector' }).click();
  await page.getByRole('tab', { name: 'Statements' }).click();
  await expect(page.getByText('public-source fact', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /Who controls the observed addresses/ })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Public-source investigation').locator('.source-result')).toHaveCount(1);
});


test('Gemini plans, collects, explains and returns analyst control at the bound', async ({ page }) => {
  const response = await page.request.post('/api/test/gemini-case');
  expect(response.ok()).toBeTruthy();
  const initial = await response.json();
  await page.goto('/#case=' + initial.investigation.id);
  await expect(page.getByRole('heading', { name: 'Ready for your next step' })).toBeVisible();
  const panel = page.getByLabel('Gemini investigation reasoning');
  await expect(panel).toContainText('2 / 2 collection steps');
  await expect(panel).toContainText('Control is with the analyst');
  await expect(page.getByLabel('Public-source investigation').locator('.source-result')).toHaveCount(1);
  await panel.getByText('Why this assessment?', { exact: true }).click();
  await expect(panel).toContainText('Who controls these addresses?');
  await panel.getByRole('button', { name: /Who controls these addresses/ }).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByRole('heading', { name: 'Why?', exact: true })).toBeVisible();
  await expect(drawer).toContainText('No ownership proof has been collected');
  await expect(drawer).toContainText('supporting evidence IDs: None');
  await page.getByRole('button', { name: 'Close inspector' }).click();
  await page.getByLabel('Recommended next step').getByTestId('next-step').click();
  await expect(page.getByText('Investigation updated', { exact: false }).first()).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Ready for your next step' })).toBeVisible();
  await expect(page.getByText('Revision 3', { exact: true })).toBeVisible();
  await expect(page.getByTestId('next-step')).toBeDisabled();
  await expect(page.getByTestId('next-step')).toContainText('Manual analyst work required');
  await page.screenshot({ path: 'test-results/gemini-workspace.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.reload();
  await expect(page.getByText('Revision 3', { exact: true })).toBeVisible();
});


test('Solana provenance, counterparty expansion and mixed-chain analyst link remain in one case', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Data mode').selectOption('live');
  const seed = 'CxegPrfn2ge5dNiQberUrQJkHCcimeR4VXkeawcFBBka';
  await page.getByLabel('Ethereum or Solana wallet 1', { exact: true }).fill(seed);
  await page.getByRole('button', { name: 'Start investigation' }).click();
  await expect(page.getByRole('heading', { name: 'Ready for your next step' })).toBeVisible();
  const originalUrl = page.url();
  const id = originalUrl.split('#case=')[1];
  const state = await (await page.request.get('/api/investigations/' + id)).json();
  const transfer = state.transactions.find((t: {chain: string}) => t.chain === 'solana');
  await page.getByLabel('Inspect graph record').selectOption(transfer.receiver);
  await page.getByRole('dialog').getByRole('button', { name: 'Expand outbound' }).click();
  await expect(page.getByRole('status', { name: 'Investigation updated' })).toContainText('revision 2');
  await page.getByLabel('Inspect graph record').selectOption(transfer.receiver);
  await page.getByRole('dialog').getByRole('button', { name: 'Inspect record evidence' }).last().click();
  await expect(page.getByRole('dialog').locator('a[href^="https://explorer.solana.com/tx/"]').first()).toBeVisible();
  await page.getByRole('button', { name: 'Close inspector' }).click();
  const scope = page.getByLabel('Chain scope', { exact: true });
  await scope.getByText('Add a wallet to this investigation', { exact: true }).click();
  await scope.getByLabel('Ethereum or Solana address').fill('0x' + 'a'.repeat(40));
  await scope.getByRole('button', { name: 'Collect added wallet' }).click();
  await expect(page.getByRole('status', { name: 'Investigation updated' })).toContainText('revision 3');
  await scope.getByText('Propose an evidence-backed cross-chain link').click();
  await scope.getByLabel('Ethereum entity').selectOption('eth-0x' + 'a'.repeat(40));
  await scope.getByLabel('Solana entity').selectOption('sol-' + seed);
  await scope.getByLabel('Supporting record').selectOption({ index: 1 });
  await scope.getByLabel('Relationship and limitations').fill('Analyst proposes a possible transition for review; bridge matching remains unverified.');
  await scope.getByRole('button', { name: 'Record proposed link' }).click();
  await expect(scope.getByText(/^INFERENCE: Analyst proposes/)).toBeVisible();
  await expect(page.getByRole('status', { name: 'Investigation updated' })).toContainText('revision 4');
  await expect(page.getByRole('heading', { name: 'Ready for your next step' })).toBeVisible();
  expect(page.url()).toBe(originalUrl);
  await page.reload();
  await expect(page.getByLabel('Chain scope').getByText(/^INFERENCE: Analyst proposes/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.screenshot({ path: 'test-results/solana-mixed-case.png', fullPage: true });
});
