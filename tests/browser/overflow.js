// Horizontal-overflow regression probe (run by tests/test_browser_mobile.py through `playwright-cli run-code`).
// __BASE__ is replaced with the app URL. Returns JSON: case -> {main, doc, frame} overflow in CSS px (0 = none).
//
// Phones enlarge text (Android font scale, iOS larger text), so every case is measured at several root font
// sizes, in true mobile emulation (isMobile, touch, DPR 3). "main" is Streamlit's scroll container: measuring
// only the document misses overflow inside it.
async page => {
  const BASE = '__BASE__';
  const browser = page.context().browser();
  const VIEWPORTS = [[390, 844], [360, 800]];
  const setScale = async (p, pct) => {
    for (const f of p.frames()) {
      try {
        await f.evaluate(s => {
          let st = document.getElementById('etp-test-scale');
          if (!st) { st = document.createElement('style'); st.id = 'etp-test-scale'; (document.head || document.documentElement).appendChild(st); }
          st.textContent = `html { font-size: ${16 * s / 100}px !important; }`;
        }, pct);
      } catch (e) { /* frame detached */ }
    }
    await p.waitForTimeout(700);
  };
  const measure = async p => {
    const m = await p.evaluate(() => {
      const main = document.querySelector('[data-testid="stMain"]');
      return { main: main ? main.scrollWidth - main.clientWidth : -1,
               doc: document.scrollingElement.scrollWidth - document.documentElement.clientWidth };
    });
    let frame = 0;
    for (const f of p.frames()) {
      if (f === p.mainFrame()) continue;
      try { frame = Math.max(frame, await f.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)); }
      catch (e) { /* frame detached */ }
    }
    return { ...m, frame };
  };
  const settle = async p => {     // walk the page so lazily rendered parts exist, then let layout settle
    for (let i = 0; i < 30; i++) { await p.mouse.wheel(0, 800); await p.waitForTimeout(60); }
    await p.waitForTimeout(1500);
  };
  const out = {};
  const record = async (p, name, scales) => {
    for (const s of scales) { await setScale(p, s); out[`${name} @${s}%`] = await measure(p); }
    await setScale(p, 100);
  };
  for (const [w, h] of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: true, hasTouch: true, deviceScaleFactor: 3 });
    const p = await ctx.newPage();
    const vp = `${w}x${h}`;
    await p.goto(BASE + '/analysis');
    await p.getByText('A synthetic demonstration image', { exact: true }).click({ timeout: 120000 });
    await p.locator('.etp-synthetic').first().waitFor({ timeout: 180000 });
    await p.locator('.etp-foot').last().waitFor({ timeout: 180000 });
    await settle(p);
    await record(p, `${vp} synthetic 2D`, [100, 125, 150, 200]);
    await p.getByText('Options: expected artifact, your regions').click();
    await p.waitForTimeout(1200);
    await record(p, `${vp} synthetic options open`, [100, 200]);
    await p.getByText('2.5D inspection', { exact: true }).click();
    await p.waitForTimeout(5000);
    await settle(p);
    await record(p, `${vp} synthetic 2.5D`, [100, 200]);
    await p.getByText('Presentation', { exact: true }).first().click();
    await p.waitForTimeout(4000);
    await settle(p);
    await record(p, `${vp} synthetic presentation`, [100, 200]);
    await p.goto(BASE + '/analysis');
    await p.getByText('A registered research photograph', { exact: true }).click({ timeout: 120000 });
    await p.locator('.etp-title-bar').first().waitFor({ timeout: 180000 });
    await p.locator('.etp-foot').last().waitFor({ timeout: 180000 });
    await settle(p);
    await record(p, `${vp} research photograph`, [100, 200]);
    await ctx.close();
  }
  return JSON.stringify(out);
}
