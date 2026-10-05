// Accessibility, fallback and performance probe (run by tests/test_browser_mobile.py through `playwright-cli
// run-code`; __BASE__ is the app URL).
//
// keyboard (real):      the first Tab reveals "Skip to main content"; the image-source radios are reachable and
//                       operable with arrow keys; the 2D / 2.5D radio group switches to 2.5D from the keyboard; no
//                       focused element is pushed off the right edge. (Focus entering Streamlit's collapsed,
//                       off-canvas sidebar on the LEFT is recorded, not judged here.)
// keyboard (synthetic): the DATA MODE switch is a radio group operable with arrow keys; "Run analysis" is reached
//                       with Tab and runs with Enter; the replay controls are real, labelled buttons.
// fallbacks:            the 2D viewer and the 2.5D view keep focus, accessible names and the flat 2D fallback;
//                       with WebGL unavailable the home-page 3D scene switches to its 2D fallback.
// motion:               prefers-reduced-motion stops the entrance animation, reaches the 2.5D view and shows the
//                       whole replay at once; without it the animation is on (so the check can fail).
// performance:          click-to-result time of the synthetic demo; frame rate of the replay and the 3D scene.
async page => {
  const BASE = '__BASE__';
  const browser = page.context().browser();
  const res = { keyboard: {}, synthetic_keyboard: {}, fallbacks: {}, motion: {}, performance: {} };
  const active = p => p.evaluate(() => {
    const a = document.activeElement, r = a ? a.getBoundingClientRect() : null;
    return { tag: a ? a.tagName : null, cls: a ? (a.className + '') : '', type: a ? a.getAttribute('type') : null,
             role: a ? a.getAttribute('role') : null, checked: a ? a.getAttribute('aria-checked') : null,
             text: a ? (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 60) : '',
             left: r ? r.left : 0, right: r ? r.right : 0, top: r ? r.top : 0, vw: document.documentElement.clientWidth };
  });
  const frameBy = async (p, title) => { for (const f of p.frames()) { try { if (await f.title() === title) return f; } catch (e) {} } return null; };
  const waitFrame = async (p, title, tries = 40) => { let f = null; for (let i = 0; i < tries && !f; i++) { f = await frameBy(p, title); if (!f) await p.waitForTimeout(500); } return f; };
  const fps = (f) => f.evaluate(() => new Promise(done => { let n = 0; const t = performance.now();
    const step = () => { n++; if (performance.now() - t < 2000) requestAnimationFrame(step); else done(Math.round(n / ((performance.now() - t) / 1000))); };
    requestAnimationFrame(step); }));

  // ---- keyboard, real research mode, 390 x 844 -------------------------------------------------
  const k = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const p = await k.newPage();
  await p.goto(BASE + '/analysis');
  await p.getByText('A registered research photograph', { exact: true }).waitFor({ timeout: 120000 });
  await p.waitForTimeout(1500);
  const skipBefore = await p.evaluate(() => { const s = document.querySelector('.etp-skip'); return s ? s.getBoundingClientRect().bottom : null; });
  await p.keyboard.press('Tab');
  await p.waitForTimeout(450);          // the skip link slides in (0.2 s transition)
  const first = await active(p);
  res.keyboard.skip_hidden_until_focus = skipBefore !== null && skipBefore <= 0;
  res.keyboard.first_tab_is_skip_link = first.cls.includes('etp-skip') && first.top >= 0;
  let radio = null;
  for (let i = 0; i < 40 && !radio; i++) {
    await p.keyboard.press('Tab');
    const a = await active(p);
    if (a.tag === 'INPUT' && a.type === 'radio') radio = a;
  }
  res.keyboard.radio_reachable_by_tab = !!radio;
  let chosen = false;
  for (let i = 0; i < 3 && radio && !chosen; i++) {
    await p.keyboard.press('ArrowDown');
    await p.waitForTimeout(500);
    chosen = await p.evaluate(() => [...document.querySelectorAll('input[type="radio"]')]
      .some(r => r.checked && (r.closest('label') || r.parentElement).innerText.includes('A registered research photograph')));
  }
  res.keyboard.research_photo_chosen_with_arrow_keys = chosen;
  try { await p.locator('.etp-title-bar').first().waitFor({ timeout: 180000 }); res.keyboard.result_shown = true; }
  catch (e) { res.keyboard.result_shown = false; }
  const pastRightEdge = [], offCanvasLeft = [];
  let stageButton = null;
  for (let i = 0; i < 80 && !stageButton; i++) {
    await p.keyboard.press('Tab');
    const a = await active(p);
    if (a.right > a.vw + 1) pastRightEdge.push(`${a.tag} ${a.text}`);
    if (a.left < -1) offCanvasLeft.push(`${a.tag} ${a.text}`);
    if (a.tag === 'BUTTON' && a.text === 'Photograph · 2D') stageButton = a;
  }
  res.keyboard.stage_view_reachable_by_tab = !!stageButton;
  res.keyboard.focused_elements_past_right_edge = pastRightEdge;
  res.keyboard.info_offcanvas_sidebar_focus_targets = offCanvasLeft.length;
  res.keyboard.page_never_scrolled_sideways = await p.evaluate(() => window.scrollX === 0
    && document.querySelector('[data-testid="stMain"]').scrollLeft === 0);
  const viewer = await waitFrame(p, 'Photograph viewer');
  res.fallbacks.viewer_2d = viewer ? await viewer.evaluate(() => {
    const v = document.getElementById('v'), img = document.getElementById('img');
    return { focusable: !!v && v.tabIndex === 0, named: !!v && (v.getAttribute('aria-label') || '').includes('Keys:'),
             image_alt: !!img && img.alt.length > 10, toolbar: !!document.querySelector('[role="toolbar"][aria-label]') };
  }) : null;
  let insp = null;
  if (stageButton) {
    await p.keyboard.press('ArrowRight');
    await p.waitForTimeout(400);
    insp = await waitFrame(p, '2.5D photograph inspection', 12);
    if (!insp) { await p.keyboard.press('Space'); insp = await waitFrame(p, '2.5D photograph inspection'); }
  }
  res.keyboard.stage_view_switches_to_25d_by_keyboard = !!insp;
  res.fallbacks.inspection_25d = insp ? await insp.evaluate(() => {
    const s = document.getElementById('stage'), flat = document.querySelector('#flat canvas'), b2d = document.getElementById('b2d');
    return { focusable: !!s && s.tabIndex === 0, named: !!s && (s.getAttribute('aria-label') || '').includes('Keys:'),
             flat_2d_fallback: !!flat && flat.getAttribute('role') === 'img' && !!flat.getAttribute('aria-label'),
             toggle_2d: !!b2d && b2d.hasAttribute('aria-pressed') && !!b2d.getAttribute('aria-label') };
  }) : null;
  await k.close();

  // ---- keyboard, synthetic demonstration, 390 x 844 ----------------------------------------------
  const s = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const q = await s.newPage();
  await q.goto(BASE + '/analysis');
  await q.getByText('Synthetic Demonstration', { exact: true }).waitFor({ timeout: 120000 });
  await q.waitForTimeout(1000);
  let modeRadio = null;
  for (let i = 0; i < 40 && !modeRadio; i++) {
    await q.keyboard.press('Tab');
    const a = await active(q);
    if (a.role === 'radio' && a.text === 'Real Research') modeRadio = a;
  }
  res.synthetic_keyboard.mode_switch_reachable_by_tab = !!modeRadio;
  res.synthetic_keyboard.default_mode_is_real = !!modeRadio && modeRadio.checked === 'true';
  if (modeRadio) {                     // ARIA radio group: arrows move within it; Space selects if arrows do not
    await q.keyboard.press('ArrowRight');
    await q.waitForTimeout(400);
    res.synthetic_keyboard.arrow_moves_to_synthetic = (await active(q)).text === 'Synthetic Demonstration';
    try { await q.locator('.etp-mode-banner').first().waitFor({ timeout: 3000 }); }
    catch (e) { await q.keyboard.press('Space'); }
  }
  try { await q.locator('.etp-mode-banner').first().waitFor({ timeout: 180000 }); res.synthetic_keyboard.mode_switched_by_keyboard = true; }
  catch (e) { res.synthetic_keyboard.mode_switched_by_keyboard = false; }
  await q.getByRole('button', { name: 'Run analysis' }).waitFor({ timeout: 180000 });
  await q.waitForTimeout(1500);        // let the rerun after the mode switch finish (it resets focus)
  let runButton = null;
  for (let i = 0; i < 60 && !runButton; i++) {
    await q.keyboard.press('Tab');
    const a = await active(q);
    if (a.tag === 'BUTTON' && a.text === 'Run analysis') runButton = a;
  }
  res.synthetic_keyboard.run_reachable_by_tab = !!runButton;
  const t0 = Date.now();
  if (runButton) { await q.keyboard.press('Enter'); }
  try { await q.locator('.etp-chain').first().waitFor({ timeout: 180000 }); res.synthetic_keyboard.run_with_enter = true; }
  catch (e) { res.synthetic_keyboard.run_with_enter = false; }
  res.performance.click_to_result_ms = Date.now() - t0;
  const replay = await waitFrame(q, 'Synthetic pipeline replay');
  if (replay) {
    res.synthetic_keyboard.replay_controls = await replay.evaluate(() => ['bPlay', 'bSkip', 'bReplay', 'b2d'].map(id => {
      const b = document.getElementById(id); return !!b && b.tagName === 'BUTTON' && b.tabIndex === 0 && !!b.getAttribute('aria-label'); }));
    res.synthetic_keyboard.replay_announces = await replay.evaluate(() => document.getElementById('live').getAttribute('aria-live'));
    await replay.locator('#bReplay').focus();
    await q.keyboard.press('Enter');
    res.performance.replay_fps = await fps(replay);
    await replay.locator('#bSkip').focus();
    await q.keyboard.press('Enter');
    res.synthetic_keyboard.skip_with_keyboard_shows_all = await replay.evaluate(() => document.querySelectorAll('li.on').length);
    res.performance.pipeline_ms_reported = await replay.evaluate(() => document.getElementById('status').textContent);
  }
  await s.close();

  // ---- reduced motion (and the no-preference control) ----------------------------------------------
  for (const pref of ['reduce', 'no-preference']) {
    const c = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true,
                                         deviceScaleFactor: 3, reducedMotion: pref });
    const r = await c.newPage();
    await r.goto(BASE + '/analysis');
    await r.locator('.etp-rise').first().waitFor({ timeout: 120000 });
    const anim = await r.evaluate(() => getComputedStyle(document.querySelector('.etp-rise')).animationName);
    let inspection = null, replayAll = null;
    if (pref === 'reduce') {
      await r.getByText('A registered research photograph', { exact: true }).click({ timeout: 120000 });
      await r.locator('.etp-title-bar').first().waitFor({ timeout: 180000 });
      await r.getByText('2.5D inspection', { exact: true }).click();
      const f = await waitFrame(r, '2.5D photograph inspection');
      inspection = f ? await f.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches) : null;
      await r.goto(BASE + '/analysis?data=synthetic');
      await r.getByRole('button', { name: 'Run analysis' }).click({ timeout: 180000 });
      await r.locator('.etp-chain').first().waitFor({ timeout: 180000 });
      const rf = await waitFrame(r, 'Synthetic pipeline replay');
      replayAll = rf ? await rf.evaluate(() => ({ on: document.querySelectorAll('li.on').length, play: document.getElementById('bPlay').textContent })) : null;
    }
    res.motion[pref] = { entrance_animation: anim, inspection_sees_reduce: inspection, replay: replayAll };
    await c.close();
  }

  // ---- the home-page 3D scene: WebGL frame rate, and the 2D fallback without WebGL ------------------
  for (const webgl of [true, false]) {
    const c = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    if (!webgl) {
      await c.addInitScript(() => { const orig = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function (type, ...a) { return /webgl/i.test(type) ? null : orig.call(this, type, ...a); }; });
    }
    const h = await c.newPage();
    await h.goto(BASE + '/');
    const scene = await waitFrame(h, '3D illustration');
    await h.waitForTimeout(3000);
    if (scene) {
      const st = await scene.evaluate(() => ({ mode: window.ETP && ETP.stats.mode, webgl: window.ETP && ETP.webgl,
        msg: (document.getElementById('msg') || {}).textContent || '', fallback: !!document.querySelector('#fallback.on') }));
      if (webgl) { st.fps = await fps(scene); res.performance.scene_3d = st; }
      else { res.fallbacks.webgl_failure = st; }
    }
    await c.close();
  }
  return JSON.stringify(res);
}
