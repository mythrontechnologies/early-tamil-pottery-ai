// Accessibility regression probe for the synthetic analysis UI at phone width (run by
// tests/test_browser_mobile.py through `playwright-cli run-code`; __BASE__ is the app URL).
//
// keyboard: the first Tab reveals "Skip to main content"; the image-source radios are reachable by Tab and
//           operable with arrow keys (synthetic mode chosen without a pointer); the 2D / 2.5D control (an ARIA
//           radio group: Tab reaches the selected option, arrows move within it) switches to 2.5D from the
//           keyboard; no focused element is pushed off the right edge (horizontal overflow). Focus entering
//           Streamlit's collapsed, off-canvas mobile sidebar (left edge) is recorded, not judged here.
// fallbacks: the 2D viewer and the 2.5D view keep their accessible names, keyboard focus and flat 2D fallback.
// motion:   with prefers-reduced-motion the entrance animation is off and the 2.5D view sees the preference;
//           without it the animation is on (so the check can fail).
async page => {
  const BASE = '__BASE__';
  const browser = page.context().browser();
  const res = { keyboard: {}, fallbacks: {}, motion: {} };
  const active = p => p.evaluate(() => {
    const a = document.activeElement, r = a ? a.getBoundingClientRect() : null;
    return { tag: a ? a.tagName : null, cls: a ? (a.className + '') : '', type: a ? a.getAttribute('type') : null,
             text: a ? (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 60) : '',
             title: a && a.tagName === 'IFRAME' ? a.title : '', left: r ? r.left : 0, right: r ? r.right : 0,
             top: r ? r.top : 0, bottom: r ? r.bottom : 0, vw: document.documentElement.clientWidth };
  });

  // ---- keyboard, 390 x 844 ----------------------------------------------------------------
  const k = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const p = await k.newPage();
  await p.goto(BASE + '/analysis');
  await p.getByText('A synthetic demonstration image', { exact: true }).waitFor({ timeout: 120000 });
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
  for (let i = 0; i < 4 && radio && !chosen; i++) {
    await p.keyboard.press('ArrowDown');
    await p.waitForTimeout(400);
    chosen = await p.evaluate(() => [...document.querySelectorAll('input[type="radio"]')]
      .some(r => r.checked && (r.closest('label') || r.parentElement).innerText.includes('A synthetic demonstration image')));
  }
  res.keyboard.synthetic_mode_chosen_with_arrow_keys = chosen;
  try { await p.locator('.etp-synthetic').first().waitFor({ timeout: 180000 }); res.keyboard.banner_shown = true; }
  catch (e) { res.keyboard.banner_shown = false; }
  const pastRightEdge = [], offCanvasLeft = [];
  let stageButton = null;
  for (let i = 0; i < 80 && !stageButton; i++) {
    await p.keyboard.press('Tab');
    const a = await active(p);
    if (a.right > a.vw + 1) pastRightEdge.push(`${a.tag} ${a.text || a.title}`);
    if (a.left < -1) offCanvasLeft.push(`${a.tag} ${a.text || a.title}`);
    if (a.tag === 'BUTTON' && a.text === 'Photograph · 2D') stageButton = a;
  }
  res.keyboard.stage_view_reachable_by_tab = !!stageButton;
  res.keyboard.focused_elements_past_right_edge = pastRightEdge;
  res.keyboard.info_offcanvas_sidebar_focus_targets = offCanvasLeft.length;
  res.keyboard.page_never_scrolled_sideways = await p.evaluate(() => window.scrollX === 0
    && document.querySelector('[data-testid="stMain"]').scrollLeft === 0);

  // ---- 2D / 3D fallbacks -------------------------------------------------------------------
  const frameBy = async title => { for (const f of p.frames()) { try { if (await f.title() === title) return f; } catch (e) {} } return null; };
  const viewer = await frameBy('Photograph viewer');
  res.fallbacks.viewer_2d = viewer ? await viewer.evaluate(() => {
    const v = document.getElementById('v'), img = document.getElementById('img');
    return { focusable: !!v && v.tabIndex === 0, named: !!v && (v.getAttribute('aria-label') || '').includes('Keys:'),
             image_alt: !!img && img.alt.length > 10, toolbar: !!document.querySelector('[role="toolbar"][aria-label]') };
  }) : null;
  let insp = null;
  if (stageButton) {
    await p.keyboard.press('ArrowRight');          // radio group: move to "2.5D inspection"
    await p.waitForTimeout(400);
    const moved = await active(p);
    res.keyboard.arrow_moves_to_25d = moved.text === '2.5D inspection';
    for (let i = 0; i < 12 && !insp; i++) { await p.waitForTimeout(500); insp = await frameBy('2.5D photograph inspection'); }
    if (!insp) { await p.keyboard.press('Space'); }   // if arrows only move focus, Space selects
    for (let i = 0; i < 40 && !insp; i++) { await p.waitForTimeout(500); insp = await frameBy('2.5D photograph inspection'); }
  }
  res.keyboard.stage_view_switches_to_25d_by_keyboard = !!insp;
  res.fallbacks.inspection_25d = insp ? await insp.evaluate(() => {
    const s = document.getElementById('stage'), flat = document.querySelector('#flat canvas'), b2d = document.getElementById('b2d');
    return { focusable: !!s && s.tabIndex === 0, named: !!s && (s.getAttribute('aria-label') || '').includes('Keys:'),
             flat_2d_fallback: !!flat && flat.getAttribute('role') === 'img' && !!flat.getAttribute('aria-label'),
             toggle_2d: !!b2d && b2d.hasAttribute('aria-pressed') && !!b2d.getAttribute('aria-label') };
  }) : null;
  await k.close();

  // ---- reduced motion (and the no-preference control) ----------------------------------------
  for (const pref of ['reduce', 'no-preference']) {
    const c = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true,
                                         deviceScaleFactor: 3, reducedMotion: pref });
    const q = await c.newPage();
    await q.goto(BASE + '/analysis');
    await q.locator('.etp-rise').first().waitFor({ timeout: 120000 });
    const anim = await q.evaluate(() => getComputedStyle(document.querySelector('.etp-rise')).animationName);
    let framePref = null;
    if (pref === 'reduce') {
      await q.getByText('A synthetic demonstration image', { exact: true }).click({ timeout: 120000 });
      await q.locator('.etp-synthetic').first().waitFor({ timeout: 180000 });
      await q.getByText('2.5D inspection', { exact: true }).click();
      for (let i = 0; i < 40 && framePref === null; i++) {
        await q.waitForTimeout(500);
        for (const f of q.frames()) {
          try { if (await f.title() === '2.5D photograph inspection') framePref = await f.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches); }
          catch (e) {}
        }
      }
    }
    res.motion[pref] = { entrance_animation: anim, inspection_sees_reduce: framePref };
    await c.close();
  }
  return JSON.stringify(res);
}
