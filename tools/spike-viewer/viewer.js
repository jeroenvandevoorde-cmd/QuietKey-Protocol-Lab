/* Gate A spike results viewer — read-only, vanilla JS, no dependencies. */
'use strict';

const RESULTS_BASE = '../../artifacts/cloakvault/spike/results/';
const TOKEN_IDS = ['T0', 'T1', 'T2', 'T3', 'T4'];
const RS_BUDGET = 34;

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (children) for (const c of children) {
    node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return node;
}

async function fetchJson(name) {
  const res = await fetch(RESULTS_BASE + name);
  if (!res.ok) throw new Error(`Failed to fetch ${name}: HTTP ${res.status}`);
  return res.json();
}

function keyOf(entry) {
  return `${entry.sheet}\u0000${entry.tid}`;
}

/* ── View 1: 27×5 decode grid ─────────────────────────────────────────────── */
function renderGrid(verdict, t0free) {
  const sheets = [...new Set(verdict.map((e) => e.sheet))].sort();
  const vMap = new Map(verdict.map((e) => [keyOf(e), e]));
  const fMap = new Map(t0free.map((e) => [keyOf(e), e]));

  const head = el('tr', null, [
    el('th', { class: 'sheet' }, ['sheet']),
    ...TOKEN_IDS.map((t) => el('th', null, [t])),
  ]);
  const rows = sheets.map((sheet) => {
    const cells = TOKEN_IDS.map((tid) => {
      const v = vMap.get(`${sheet}\u0000${tid}`);
      const f = fMap.get(`${sheet}\u0000${tid}`);
      if (!v || !f) return el('td', null, ['—']);
      const delta = f.ok !== f.prev_ok ? ' Δ' : '';
      return el('td', null, [
        el('div', { class: 'cell-pair' }, [
          el('span', { class: v.ok ? 'ok' : 'bad', title: 'T0-selected (verdict)' },
            [v.ok ? 'ok' : 'fail']),
          el('span', { class: f.ok ? 'ok' : 'bad',
              title: `T0-free (prev_ok: ${f.prev_ok})` },
            [(f.ok ? 'ok' : 'fail') + delta]),
        ]),
      ]);
    });
    return el('tr', null, [el('td', { class: 'sheet' }, [sheet]), ...cells]);
  });

  const table = el('table', null, [head, ...rows]);
  const grid = document.getElementById('grid');
  grid.appendChild(el('p', { class: 'note' },
    [`${sheets.length} sheets × ${TOKEN_IDS.length} tokens; ` +
     `T0-selected ok: ${verdict.filter((e) => e.ok).length}/${verdict.length}, ` +
     `T0-free ok: ${t0free.filter((e) => e.ok).length}/${t0free.length}`]));
  grid.appendChild(table);
}

/* ── View 2: family × severity C/e/w table (tid ≠ T0) ─────────────────────── */
function renderFamSev(verdict) {
  const agg = new Map();
  for (const e of verdict) {
    if (e.tid === 'T0') continue;
    const key = `${e.fam}\u0000${e.sev}`;
    if (!agg.has(key)) {
      agg.set(key, { fam: e.fam, sev: e.sev, tokens: 0, C: 0, e: 0, w: 0 });
    }
    const a = agg.get(key);
    a.tokens += 1;
    a.C += e.C;
    a.e += e.e;
    a.w += e.w;
  }
  const rows = [...agg.values()].sort(
    (a, b) => a.fam.localeCompare(b.fam) || a.sev - b.sev,
  );

  const table = el('table', null, [
    el('tr', null, ['family', 'severity', 'tokens', 'C (correct)',
      'e (erasure)', 'w (silent wrong)'].map((h) => el('th', null, [h]))),
    ...rows.map((r) => el('tr', null, [
      el('td', { class: 'sheet' }, [r.fam]),
      el('td', { class: 'num' }, [String(r.sev)]),
      el('td', { class: 'num' }, [String(r.tokens)]),
      el('td', { class: 'num' }, [String(r.C)]),
      el('td', { class: 'num' }, [String(r.e)]),
      el('td', { class: 'num' }, [String(r.w)]),
    ])),
  ]);
  document.getElementById('famsev').appendChild(table);
}

/* ── View 3: failed tokens vs budget ──────────────────────────────────────── */
function renderFailures(verdict, t0free) {
  const failed = [];
  for (const e of verdict) {
    if (e.ok === false) failed.push({ path: 'T0-selected', ...e });
  }
  for (const e of t0free) {
    if (e.ok === false) failed.push({ path: 'T0-free', ...e });
  }
  failed.sort((a, b) =>
    a.sheet.localeCompare(b.sheet) || a.tid.localeCompare(b.tid) ||
    a.path.localeCompare(b.path));

  const table = el('table', null, [
    el('tr', null, ['path', 'sheet', 'tid', 'family', 'sev', 'Eb', 'eb',
      '2·Eb+eb', `budget ${RS_BUDGET}`].map((h) => el('th', null, [h]))),
    ...failed.map((r) => {
      const load = 2 * r.Eb + r.eb;
      const over = load > RS_BUDGET;
      return el('tr', null, [
        el('td', null, [r.path]),
        el('td', { class: 'sheet' }, [r.sheet]),
        el('td', null, [r.tid]),
        el('td', { class: 'sheet' }, [r.fam]),
        el('td', { class: 'num' }, [String(r.sev)]),
        el('td', { class: 'num' }, [String(r.Eb)]),
        el('td', { class: 'num' }, [String(r.eb)]),
        el('td', { class: over ? 'num over' : 'num' }, [String(load)]),
        el('td', null, [over ? 'over budget' : 'within budget']),
      ]);
    }),
  ]);
  const div = document.getElementById('failures');
  div.appendChild(el('p', { class: 'note' },
    [`${failed.length} failing token entries across both paths`]));
  div.appendChild(table);
}

/* ── Boot ─────────────────────────────────────────────────────────────────── */
(async () => {
  try {
    const [verdict, t0free] = await Promise.all([
      fetchJson('verdict_tokens.json'),
      fetchJson('t0free_tokens.json'),
    ]);
    renderGrid(verdict, t0free);
    renderFamSev(verdict);
    renderFailures(verdict, t0free);
  } catch (err) {
    document.getElementById('error').textContent =
      `Could not load spike results: ${err.message}\n` +
      'Serve the repository root with a static file server and open ' +
      'tools/spike-viewer/ from there.';
  }
})();
