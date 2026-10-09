// In-app navigation probe (run by tests/test_browser_mobile.py through `playwright-cli run-code`; __BASE__ is the
// app URL). Returns JSON: {first_load, deselect, cases}.
//
// The other probes open every page with its own page load, i.e. a fresh Streamlit session per page. People
// change pages through the app's navigation inside ONE session, and that is where the view mode used to break:
// the Research / Presentation switch is a different widget on every page, so a page switch dropped the chosen
// mode and a return visit left it None; the page's next run crashed in boot() ("'NoneType' object has no
// attribute 'lower'"), as did clicking the selected mode. For phone, tablet and desktop width, in a fresh session:
//
// * first_load: the mode the switch shows on the first page (the default, Research);
// * deselect:   the mode after clicking the already-selected mode (it must stay selected);
// * cases:      for Research, then Presentation, every page reached through the navigation (and back again):
//               the mode the switch shows on arrival, an exception, a heading, on Analysis the Synthetic
//               Demonstration data mode (the page's next run: on the return visit this is what crashed; on desktop
//               also a synthetic run in the current view mode, first visit), the mode after switching it on the
//               page and back, and horizontal overflow with text at 100-200 % (forward pass).
// Read-only: no annotation is saved; the synthetic run writes nothing.
async page => {
  const BASE = '__BASE__';
  const browser = page.context().browser();
  const PAGES = [['analysis', '/analysis'], ['annotation', '/annotation'], ['dataset', '/dataset'],
                 ['evidence', '/evidence'], ['workflow', '/workflow'], ['about', '/about'], ['overview', '/']];
  const ROUTE = [...PAGES, ...PAGES.slice(0, -1).reverse()];        // forward, then back: every neighbour pair
  const VIEWPORTS = [[390, 844, true], [768, 1024, true], [1280, 800, false]];
  const SCALES = [100, 125, 150, 175, 200];
  const idle = async p => {                     // the script run has finished and nothing is stale
    let quiet = 0;
    for (let i = 0; i < 900 && quiet < 4; i++) {
      await p.waitForTimeout(250);
      const busy = await p.evaluate(() => !!document.querySelector('[data-testid="stStatusWidget"], [data-stale="true"]'));
      quiet = busy ? 0 : quiet + 1;
    }
  };
  const shown = p => p.evaluate(() => [...document.querySelectorAll('.st-key-etp_mode_switch [role="radio"]')]
    .filter(b => b.getAttribute('aria-checked') === 'true').map(b => b.innerText.trim()).join('+') || 'none');
  const errors = p => p.evaluate(() => document.querySelectorAll('[data-testid="stException"]').length);
  const pick = async (p, scope, label) => {
    const b = p.locator(`${scope} [role="radio"]`).filter({ hasText: new RegExp(`^${label}$`) }).first();
    if (!await b.count()) return false;                               // the page failed before the control
    await b.click();
    await idle(p);
    return true;
  };
  const navigate = async (p, path) => {         // the app's own navigation: top bar, or the sidebar on a phone
    const found = await p.evaluate(path => {
      const a = [...document.querySelectorAll('[data-testid="stTopNavLink"], [data-testid="stSidebarNavLink"]')]
        .find(x => new URL(x.href).pathname === path);
      if (a) a.click();
      return !!a;
    }, path);
    await p.waitForURL(u => u.pathname === path, { timeout: 60000 });          // u is a URL object
    await p.locator('.st-key-etp_mode_switch [role="radio"], [data-testid="stException"]').first().waitFor({ timeout: 180000 });
    await idle(p);
    return found;
  };
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
  const overflow = async p => {
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
    return Math.max(m.main, m.doc, frame);
  };
  const settle = async p => {
    for (let i = 0; i < 25; i++) { await p.mouse.wheel(0, 800); await p.waitForTimeout(60); }
    await p.waitForTimeout(1200);
    await p.mouse.wheel(0, -100000);
    await p.waitForTimeout(300);
  };
  const out = { first_load: {}, deselect: {}, cases: {} };
  for (const [w, h, mobile] of VIEWPORTS) {
    const vp = `${w}x${h}`;
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile,
                                           deviceScaleFactor: mobile ? 3 : 1 });
    const p = await ctx.newPage();
    await p.goto(BASE + '/');
    await p.locator('.st-key-etp_mode_switch [role="radio"]').first().waitFor({ timeout: 180000 });
    await idle(p);
    out.first_load[vp] = await shown(p);
    await pick(p, '.st-key-etp_mode_switch', 'Research');            // click the selected mode
    out.deselect[vp] = { shown: await shown(p), exception: await errors(p) };
    for (const mode of ['Research', 'Presentation']) {
      const other = mode === 'Research' ? 'Presentation' : 'Research';
      if (mode === 'Presentation') await pick(p, '.st-key-etp_mode_switch', 'Presentation');
      for (const [i, [name, path]] of ROUTE.entries()) {
        const c = { linked: await navigate(p, path) };
        c.on_arrival = await shown(p);
        c.exception = await errors(p);
        c.heading = await p.evaluate(() => !!document.querySelector('h1, h2, .etp-title-bar'));
        if (name === 'analysis') {                       // Synthetic Demonstration: the page's next run
          await pick(p, '.st-key-data_mode', 'Synthetic Demonstration');
          c.synthetic_banner = await p.locator('.etp-mode-banner').count() > 0;
          c.exception += await errors(p);
          if (!mobile && i < PAGES.length && !c.exception) {          // one synthetic run per mode (desktop)
            await p.getByRole('button', { name: 'Run analysis' }).click();
            await p.locator('[aria-label="Synthetic result status"]').first().waitFor({ timeout: 300000 });
            await idle(p);
            c.synthetic_result = true;
            c.exception += await errors(p);
          }
        }
        await pick(p, '.st-key-etp_mode_switch', other);
        c.switched = await shown(p);
        await pick(p, '.st-key-etp_mode_switch', mode);
        c.switched_back = await shown(p);
        c.exception += await errors(p);
        if (i < PAGES.length) {                                       // text sizes, on the forward pass
          await settle(p);
          c.overflow = {};
          for (const s of SCALES) { await setScale(p, s); c.overflow[`${s}%`] = await overflow(p); }
          await setScale(p, 100);
        }
        out.cases[`${vp} ${mode} ${name}${i < PAGES.length ? '' : ' (back)'}`] = c;
      }
    }
    await ctx.close();
  }
  return JSON.stringify(out);
}
