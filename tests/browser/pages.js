// Every-page layout probe (run by tests/test_browser_mobile.py through `playwright-cli run-code`).
// __BASE__ is replaced with the app URL. Returns JSON: case -> {main, doc, frame, exception, heading}.
//
// Milestone 11: the overflow probe covered the Analysis page only. This one visits every page of the app at
// phone, tablet and desktop width, with text at 100 / 125 / 150 / 175 / 200 % (phones and browsers enlarge
// text), and records horizontal overflow (CSS px; 0 = none), whether Streamlit raised an exception on the
// page, and whether the page rendered its heading. Read-only: nothing is saved on any page.
async page => {
  const BASE = '__BASE__';
  const browser = page.context().browser();
  const PAGES = [['overview', ''], ['annotation', '/annotation'], ['dataset', '/dataset'],
                 ['evidence', '/evidence'], ['workflow', '/workflow'], ['about', '/about']];
  const VIEWPORTS = [[390, 844, true], [768, 1024, true], [1280, 800, false]];
  const SCALES = [100, 125, 150, 175, 200];
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
    await p.waitForTimeout(600);
  };
  const measure = async p => {
    const m = await p.evaluate(() => {
      const main = document.querySelector('[data-testid="stMain"]');
      return { main: main ? main.scrollWidth - main.clientWidth : -1,
               doc: document.scrollingElement.scrollWidth - document.documentElement.clientWidth,
               exception: document.querySelectorAll('[data-testid="stException"]').length,
               heading: !!document.querySelector('h1, h2, .etp-title-bar') };
    });
    let frame = 0;
    for (const f of p.frames()) {
      if (f === p.mainFrame()) continue;
      try { frame = Math.max(frame, await f.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)); }
      catch (e) { /* frame detached */ }
    }
    return { ...m, frame };
  };
  const settle = async p => {
    for (let i = 0; i < 25; i++) { await p.mouse.wheel(0, 800); await p.waitForTimeout(60); }
    await p.waitForTimeout(1200);
  };
  const out = {};
  for (const [w, h, mobile] of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile,
                                           deviceScaleFactor: mobile ? 3 : 1 });
    const p = await ctx.newPage();
    for (const [name, path] of PAGES) {
      await p.goto(BASE + path);
      await p.locator('[data-testid="stMain"]').first().waitFor({ timeout: 180000 });
      await p.waitForTimeout(4000);
      await settle(p);
      for (const s of SCALES) { await setScale(p, s); out[`${w}x${h} ${name} @${s}%`] = await measure(p); }
      await setScale(p, 100);
    }
    await ctx.close();
  }
  return JSON.stringify(out);
}
