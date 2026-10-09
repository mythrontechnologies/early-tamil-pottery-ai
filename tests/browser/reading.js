// Language / reading results probe (run by tests/test_browser_mobile.py through `playwright-cli run-code`;
// __BASE__ is the app URL). Returns JSON: case -> {fields, translation, transliteration, evidence, offscreen,
// overflow{scale: px}} and, for synthetic runs, the pipeline replay's per-stage reading lines.
//
// At phone, tablet and desktop width, in Research and Presentation mode, for a synthetic demonstration run and a
// registered research photograph: the section exists with its five fields, the translation and transliteration
// are stated in their own fields (never left to the reasoning text), no card is pushed off screen, and the page
// does not overflow sideways with text at 100-200 %. Read-only: nothing is saved.
async page => {
  const BASE = '__BASE__';
  const browser = page.context().browser();
  const VIEWPORTS = [[390, 844, true], [768, 1024, true], [1280, 800, false]];
  const SCALES = [100, 150, 200];
  const idle = async p => {
    let quiet = 0;
    for (let i = 0; i < 900 && quiet < 4; i++) {
      await p.waitForTimeout(250);
      const busy = await p.evaluate(() => !!document.querySelector('[data-testid="stStatusWidget"], [data-stale="true"]'));
      quiet = busy ? 0 : quiet + 1;
    }
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
    await p.waitForTimeout(700);
  };
  const overflow = async p => {
    const m = await p.evaluate(() => {
      const main = document.querySelector('[data-testid="stMain"]');
      return Math.max(main ? main.scrollWidth - main.clientWidth : -1,
                      document.scrollingElement.scrollWidth - document.documentElement.clientWidth);
    });
    let frame = 0;
    for (const f of p.frames()) {
      if (f === p.mainFrame()) continue;
      try { frame = Math.max(frame, await f.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)); }
      catch (e) { /* frame detached */ }
    }
    return Math.max(m, frame);
  };
  const settle = async p => {
    for (let i = 0; i < 40; i++) { await p.mouse.wheel(0, 800); await p.waitForTimeout(60); }
    await p.waitForTimeout(1500);
  };
  const section = p => p.evaluate(() => {
    const s = document.querySelector('.etp-reading');
    if (!s) return null;
    const vw = document.documentElement.clientWidth;
    const cards = [...s.querySelectorAll('.etp-reading-field')];
    const val = label => { const c = cards.find(x => x.querySelector('.k').textContent.trim() === label);
                           return c ? c.querySelector('.v').textContent.trim() : null; };
    return { fields: cards.map(c => c.querySelector('.k').textContent.trim()),
             translation: val('Translation'), transliteration: val('Transliteration'), transcription: val('Transcription'),
             evidence: cards.some(c => [...c.querySelectorAll('.who')].some(w => w.textContent.startsWith('Evidence:'))),
             visible: s.getBoundingClientRect().height > 0,
             offscreen: cards.filter(c => { const r = c.getBoundingClientRect(); return r.left < -1 || r.right > vw + 1; }).length };
  });
  const measure = async (p, name) => {
    await settle(p);
    const c = await section(p);
    if (c) {
      c.overflow = {};
      for (const s of SCALES) { await setScale(p, s); c.overflow[`${s}%`] = await overflow(p); }
      await setScale(p, 100);
    }
    out[name] = c;
  };
  const presentation = async p => {
    await p.locator('.st-key-etp_mode_switch [role="radio"]').filter({ hasText: /^Presentation$/ }).first().click();
    await idle(p);
    await p.locator('.etp-reading').first().waitFor({ timeout: 180000 });
  };
  const out = {};
  for (const [w, h, mobile] of VIEWPORTS) {
    const vp = `${w}x${h}`;
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile,
                                           deviceScaleFactor: mobile ? 3 : 1 });
    const p = await ctx.newPage();
    // synthetic demonstration
    await p.goto(BASE + '/analysis?data=synthetic');
    await p.getByRole('button', { name: 'Run analysis' }).click({ timeout: 180000 });
    await p.locator('.etp-reading').first().waitFor({ timeout: 300000 });
    await idle(p);
    let replay = null;
    for (let i = 0; i < 40 && !replay; i++) {
      for (const f of p.frames()) { try { if (await f.title() === 'Synthetic pipeline replay') replay = f; } catch (e) {} }
      if (!replay) await p.waitForTimeout(500);
    }
    if (replay) {
      await replay.locator('#bSkip').click();
      await p.waitForTimeout(400);
      out[`${vp} replay`] = await replay.evaluate(() => [...document.querySelectorAll('li')].map(li => ({
        title: li.querySelector('.t span').textContent, on: li.classList.contains('on'),
        details: [...li.querySelectorAll('.d')].map(d => d.textContent) })));
    }
    await measure(p, `${vp} synthetic Research`);
    await presentation(p);
    await measure(p, `${vp} synthetic Presentation`);
    // real research mode: a registered research photograph
    await p.goto(BASE + '/analysis');
    await p.getByText('A registered research photograph', { exact: true }).click({ timeout: 120000 });
    await p.locator('.etp-reading').first().waitFor({ timeout: 180000 });
    await idle(p);
    await measure(p, `${vp} research Research`);
    await presentation(p);
    await measure(p, `${vp} research Presentation`);
    await ctx.close();
  }
  return JSON.stringify(out);
}
