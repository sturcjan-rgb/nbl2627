/* NBL 2026/27 — ligové statistiky. Statický frontend nad JSONy v data/<sezóna>/ a živou větví „live“. */
(function () {
'use strict';

const REPO = 'sturcjan-rgb/nbl2627';
const SEASON = '2026-27';
const DATA_REL = 'data/' + SEASON + '/';
// větev s daty = výchozí větev repa; při otevření z GitHub Pages se čte relativně
const DATA_RAW = 'https://raw.githubusercontent.com/' + REPO + '/HEAD/' + DATA_REL;
const LIVE_RAW = 'https://raw.githubusercontent.com/' + REPO + '/live/';
const LIVE_POLL_MS = 5000;

const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const f1 = x => x == null || isNaN(x) ? '—' : (Math.round(x * 10) / 10).toFixed(1);
const f0 = x => x == null || isNaN(x) ? '—' : String(Math.round(x));
const pctS = x => x == null ? '—' : f1(x);
const signed = x => x == null || isNaN(x) ? '—' : (x > 0 ? '+' : '') + (Number.isInteger(x) ? x : f1(x));
const cls = x => x > 0 ? 'pos' : x < 0 ? 'neg' : '';
const fmtDate = iso => { if (!iso) return ''; const d = new Date(iso); return d.toLocaleDateString('cs-CZ', {day: 'numeric', month: 'numeric', timeZone: 'Europe/Prague'}) + ' ' + d.toLocaleTimeString('cs-CZ', {hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Prague'}); };
const fmtDay = iso => iso ? new Date(iso).toLocaleDateString('cs-CZ', {weekday: 'short', day: 'numeric', month: 'numeric', timeZone: 'Europe/Prague'}) : '';

/* ---------------- data ---------------- */
const cache = {};
async function getJSON(path) {
  if (cache[path]) return cache[path];
  const tries = location.protocol.startsWith('http') && !location.hostname.endsWith('githubusercontent.com')
    ? [DATA_REL + path, DATA_RAW + path] : [DATA_RAW + path];
  let err;
  for (const u of tries) {
    try {
      const r = await fetch(u, {cache: 'no-cache'});
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      cache[path] = j;
      return j;
    } catch (e) { err = e; }
  }
  throw new Error('Nepodařilo se načíst ' + path + ' (' + (err && err.message) + ')');
}
async function getLive(name) {
  // raw.githubusercontent drží soubory 5 min v cache → soubory po 5s oknech (jako srsni-data)
  const b = Math.floor(Date.now() / 5000);
  const urls = [2, 3, 4, 5].map(k => LIVE_RAW + name + '/' + (b - k) + '.json').concat(LIVE_RAW + name + '.json');
  for (const u of urls) {
    try { const r = await fetch(u, {cache: 'no-store'}); if (r.ok) return await r.json(); } catch (e) { /* další */ }
  }
  return null;
}

let TEAMS = {};   // slug -> {name,label,logo}
async function base() {
  const idx = await getJSON('index.json');
  TEAMS = {};
  for (const t of idx.teams || []) TEAMS[t.slug] = t;
  $('#stamp').textContent = 'data ' + new Date(idx.generatedAt).toLocaleString('cs-CZ');
  return idx;
}
const logo = slug => TEAMS[slug] && TEAMS[slug].logo ? `<img class="tlogo" src="${esc(TEAMS[slug].logo)}" alt="" loading="lazy" onerror="this.remove()">` : '';
const teamA = (slug, name) => `<a class="team-link" href="#/tym/${esc(slug)}">${logo(slug)}${esc(name || (TEAMS[slug] || {}).name || slug)}</a>`;
const label = slug => (TEAMS[slug] || {}).label || slug;

/* ---------------- tabulka s řazením ---------------- */
// cols: [{k, t, get(row), fmt(v,row), l (vlevo), s (řaditelné), desc (výchozí sestupně), title}]
function sortTable(el, cols, rows, opts = {}) {
  let key = opts.sort || null, dir = opts.dir || -1;
  function draw() {
    const c = cols.find(x => x.k === key);
    const data = rows.slice();
    if (c) data.sort((a, b) => {
      const va = c.get(a), vb = c.get(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return (typeof va === 'string' ? va.localeCompare(vb, 'cs') : va - vb) * dir;
    });
    const head = cols.map((x, i) => `<th class="${x.l ? 'l' : ''} ${x.s !== false ? 's' : ''} ${x.k === key ? 'on' : ''} ${i === 0 && opts.stickyFirst ? 'sticky' : ''}" data-k="${x.k}" title="${esc(x.title || '')}">${x.t}${x.k === key ? (dir < 0 ? ' ▾' : ' ▴') : ''}</th>`).join('');
    const body = data.map((r, ri) => `<tr${opts.rowClass ? ` class="${opts.rowClass(r)}"` : ''}>` + cols.map((x, i) => {
      const v = x.get(r);
      return `<td class="${x.l ? 'l' : ''} ${x.cls ? x.cls(v, r) : ''} ${i === 0 && opts.stickyFirst ? 'sticky' : ''}">${x.fmt ? x.fmt(v, r, ri) : (v == null ? '—' : esc(v))}</td>`;
    }).join('') + '</tr>').join('');
    el.innerHTML = `<div class="tw"><table><thead><tr>${head}</tr></thead><tbody>${body || `<tr><td class="l muted" colspan="${cols.length}">Zatím žádná data.</td></tr>`}</tbody>${opts.foot || ''}</table></div>`;
    el.querySelectorAll('th.s').forEach(th => th.onclick = () => {
      const k = th.dataset.k, c2 = cols.find(x => x.k === k);
      if (key === k) dir = -dir; else { key = k; dir = c2.asc ? 1 : -1; }
      draw();
    });
  }
  draw();
}
const rk = (ranks, k) => {
  if (!ranks || ranks[k] == null) return '';
  const r = ranks[k], of = ranks.of || 12;
  return `<span class="rk ${r <= 3 ? 'top' : r > of - 3 ? 'bot' : ''}">${r}.</span>`;
};

/* ---------------- routing ---------------- */
const routes = [
  [/^#?\/?$/, viewHome, 'home'],
  [/^#\/zapasy$/, viewGames, 'zapasy'],
  [/^#\/liga$/, viewLeague, 'liga'],
  [/^#\/hraci$/, viewPlayers, 'hraci'],
  [/^#\/zebricky$/, viewLeaders, 'zebricky'],
  [/^#\/tym\/([\w-]+)$/, viewTeam, 'tym'],
  [/^#\/zapas\/(\d+)$/, viewMatch, 'zapas'],
];
let liveTimer = null;
async function route() {
  if (liveTimer) { clearInterval(liveTimer); liveTimer = null; }
  const h = location.hash || '#/';
  const app = $('#app');
  for (const [re, fn, nav] of routes) {
    const m = h.match(re);
    if (!m) continue;
    document.querySelectorAll('nav.main a').forEach(a => a.classList.toggle('active', a.dataset.nav === nav));
    app.innerHTML = '<div class="loading">Načítám…</div>';
    try {
      await base();
      await fn(app, ...m.slice(1));
    } catch (e) {
      console.error(e);
      app.innerHTML = `<div class="err">${esc(e.message)}</div>`;
    }
    window.scrollTo(0, 0);
    return;
  }
  location.hash = '#/';
}
window.addEventListener('hashchange', route);

/* ---------------- karty zápasů ---------------- */
function gameCard(f, live) {
  const st = live ? live.status : f.status;
  const sc = live && live.score ? {home: live.score[0], away: live.score[1]} : f.score;
  const hw = sc && st === 'final' && sc.home > sc.away, aw = sc && st === 'final' && sc.away > sc.home;
  const meta = st === 'live' ? `<span class="badge live">živě</span> ${esc(live && live.period || '')} ${esc(live && live.clock || '')}`
    : st === 'final' ? 'konec' : fmtDate(f.datetime);
  const href = f.fibaId && (f.hasStats || st === 'live' || live) ? `#/zapas/${f.fibaId}` : null;
  const inner = `<div class="meta"><span>${esc(f.round || '')}</span><span>${meta}</span></div>
    <div class="row ${hw ? 'win' : ''}"><span class="t">${logo(f.homeSlug)}${esc(label(f.homeSlug) || f.home)}</span><span class="s">${sc ? sc.home : ''}</span></div>
    <div class="row ${aw ? 'win' : ''}"><span class="t">${logo(f.awaySlug)}${esc(label(f.awaySlug) || f.away)}</span><span class="s">${sc ? sc.away : ''}</span></div>`;
  return href ? `<a class="game ${st === 'live' ? 'is-live' : ''}" href="${href}">${inner}</a>` : `<div class="game">${inner}</div>`;
}

function standingsTable(el, table, compact) {
  const cols = [
    {k: 'pos', t: '#', get: r => r.pos, asc: true},
    {k: 'team', t: 'Tým', l: true, get: r => r.name, fmt: (v, r) => teamA(r.slug, compact ? r.label : r.name), asc: true},
    {k: 'gp', t: 'Z', get: r => r.gp},
    {k: 'w', t: 'V', get: r => r.w},
    {k: 'l', t: 'P', get: r => r.l, asc: true},
    {k: 'pct', t: '%', get: r => r.pct, fmt: v => f0(v * 100)},
    {k: 'score', t: 'Skóre', get: r => r.pf, fmt: (v, r) => r.pf + ':' + r.pa},
    {k: 'diff', t: '+/−', get: r => r.diff, fmt: signed, cls: cls},
  ];
  if (!compact) cols.push(
    {k: 'ppg', t: 'Body', get: r => r.ppg, fmt: f1},
    {k: 'oppg', t: 'Obdr.', get: r => r.oppg, fmt: f1, asc: true},
    {k: 'home', t: 'Doma', get: r => r.home, s: false},
    {k: 'away', t: 'Venku', get: r => r.away, s: false},
    {k: 'close', t: 'Těsné', get: r => r.close, s: false, title: 'zápasy rozhodnuté o 5 a méně bodů'},
    {k: 'streak', t: 'Série', get: r => r.streak, s: false});
  cols.push({k: 'last5', t: 'Forma', get: r => r.last5, s: false, fmt: v => `<span class="form">${(v || '').split('').map(x => `<span class="${x}">${x === 'W' ? 'V' : 'P'}</span>`).join('')}</span>`});
  sortTable(el, cols, table, {sort: 'pos', dir: 1});
}

/* ---------------- PŘEHLED ---------------- */
async function viewHome(app) {
  const [st, sch, lead] = await Promise.all([getJSON('standings.json'), getJSON('schedule.json'), getJSON('leaders.json')]);
  const fx = sch.fixtures;
  const now = Date.now();
  const played = fx.filter(f => f.status === 'final').sort((a, b) => b.datetime.localeCompare(a.datetime));
  const upcoming = fx.filter(f => f.status !== 'final' && new Date(f.datetime).getTime() > now - 3 * 3600e3).sort((a, b) => a.datetime.localeCompare(b.datetime));
  const lastRound = played[0] && played[0].round;
  app.innerHTML = `
    <section id="live-sec" class="hidden"><h2><span class="badge live">živě</span> Dnes</h2><div class="games" id="live-games"></div></section>
    <div class="grid g2">
      <section><h2>Tabulka</h2><div id="tbl"></div><div class="caption">Při shodě rozhodují vzájemné zápasy, pak celkový rozdíl skóre. Klikni na záhlaví pro řazení.</div></section>
      <section>
        <h2>Nejbližší zápasy</h2><div class="games">${upcoming.slice(0, 6).map(f => gameCard(f)).join('') || '<div class="muted">Sezóna dohraná.</div>'}</div>
        <h2 style="margin-top:22px">Poslední výsledky${lastRound ? ' · ' + esc(lastRound) : ''}</h2><div class="games">${played.slice(0, 6).map(f => gameCard(f)).join('')}</div>
        <div class="caption"><a href="#/zapasy">Všechny zápasy →</a></div>
      </section>
    </div>
    <section><h2>Lídři ligy</h2><div class="grid g4">${['pts', 'reb', 'ast', 'eff'].map(k => leaderCard(lead[k], 5)).join('')}</div>
      <div class="caption"><a href="#/zebricky">Všechny žebříčky →</a> · min. ${lead.minGames} zápasů</div></section>`;
  standingsTable($('#tbl'), st.table, true);
  // dnešní zápasy živě
  const pollToday = async () => {
    const idx = await getLive('index');
    const sec = $('#live-sec');
    if (!sec) return;
    const today = new Date().toDateString();
    const rows = idx && new Date(idx.updatedAt).toDateString() === today ? idx.today : [];
    if (!rows.length) { sec.classList.add('hidden'); return; }
    sec.classList.remove('hidden');
    $('#live-games').innerHTML = rows.map(r => gameCard({...r, status: r.status}, r)).join('');
  };
  pollToday();
  liveTimer = setInterval(pollToday, 15000);
}

function leaderCard(L, n) {
  if (!L) return '';
  return `<div class="panel"><h3>${esc(L.label)}</h3><div class="tx"><table class="lead">${L.rows.slice(0, n).map((r, i) =>
    `<tr><td class="l muted">${i + 1}.</td><td class="l name">${esc(r.name)} <span class="muted">${esc(r.teamLabel)}</span></td><td><b>${f1(r.value)}</b></td></tr>`).join('')}</table></div></div>`;
}

/* ---------------- ZÁPASY ---------------- */
async function viewGames(app) {
  const sch = await getJSON('schedule.json');
  const fx = sch.fixtures;
  const teams = Object.keys(TEAMS).sort((a, b) => label(a).localeCompare(label(b), 'cs'));
  app.innerHTML = `<h1>Zápasy</h1><div class="toolbar" style="margin-top:14px">
    <select id="fTeam"><option value="">Všechny týmy</option>${teams.map(s => `<option value="${s}">${esc(TEAMS[s].name)}</option>`).join('')}</select>
    <select id="fState"><option value="">Vše</option><option value="final">Odehrané</option><option value="scheduled">Budoucí</option></select></div>
    <div id="rounds"></div>`;
  const draw = () => {
    const t = $('#fTeam').value, s = $('#fState').value;
    const list = fx.filter(f => (!t || f.homeSlug === t || f.awaySlug === t) && (!s || (s === 'final' ? f.status === 'final' : f.status !== 'final')));
    const byRound = {};
    for (const f of list) (byRound[f.roundNum || 0] = byRound[f.roundNum || 0] || []).push(f);
    $('#rounds').innerHTML = Object.keys(byRound).sort((a, b) => a - b).map(r =>
      `<section><h2>${r === '0' ? 'Ostatní' : r + '. kolo'} <span class="muted" style="text-transform:none">${fmtDay(byRound[r][0].datetime)}</span></h2><div class="games">${byRound[r].map(f => gameCard(f)).join('')}</div></section>`).join('') || '<div class="muted">Nic.</div>';
  };
  $('#fTeam').onchange = draw; $('#fState').onchange = draw;
  draw();
}

/* ---------------- LIGA (srovnání týmů) ---------------- */
async function viewLeague(app) {
  const lg = await getJSON('league.json');
  const avg = lg.averages || {};
  let mode = 'adv';
  app.innerHTML = `<h1>Srovnání týmů</h1><p class="muted">Pokročilé metriky ze součtů celé sezóny. Malé číslo za hodnotou = pořadí v lize (zelená top 3, červená poslední 3).</p>
    <div class="tabs" id="modes"><button data-m="adv" class="on">Útok & obrana</button><button data-m="ff">Four factors</button><button data-m="shoot">Střelba</button><button data-m="box">Na zápas</button><button data-m="misc">Clutch & čas útoku</button></div>
    <div id="lt"></div><div class="caption" id="lnote"></div>`;
  const T = lg.teams;
  const team = {k: 'team', t: 'Tým', l: true, get: r => r.label, fmt: (v, r) => teamA(r.slug, r.label), asc: true};
  const A = (k, t, opt = {}) => ({k, t, get: r => (opt.src ? opt.src(r) : r.adv)[k], fmt: (v, r) => (opt.f || f1)(v) + rk(r.ranks, opt.rk || k), asc: opt.asc, title: opt.title});
  const sets = {
    adv: [team, {k: 'wl', t: 'V-P', get: r => r.w, fmt: (v, r) => r.w + '-' + r.l},
      A('ortg', 'ORtg', {title: 'body na 100 držení'}), A('drtg', 'DRtg', {asc: true, title: 'obdržené body na 100 držení'}),
      {k: 'net', t: 'Net', get: r => r.adv.net, fmt: (v, r) => `<b class="${cls(v)}">${signed(v)}</b>` + rk(r.ranks, 'net')},
      A('pace', 'Pace', {title: 'držení na 40 minut'}), A('ts', 'TS%'), A('efg', 'eFG%'),
      {k: 'ppg', t: 'Body', get: r => r.perGame.ppg, fmt: (v, r) => f1(v) + rk(r.ranks, 'ppg')},
      {k: 'oppg', t: 'Obdr.', get: r => r.perGame.oppg, fmt: (v, r) => f1(v) + rk(r.ranks, 'oppg'), asc: true}],
    ff: [team, A('efg', 'eFG%'), A('tov', 'TOV%', {asc: true}), A('orb', 'ORB%'), A('ftr', 'FT rate'),
      {k: 'opp_efg', t: 'Soup. eFG%', get: r => r.oppAdv.opp_efg, fmt: (v, r) => f1(v) + rk(r.ranks, 'opp_efg'), asc: true},
      {k: 'opp_tov', t: 'Soup. TOV%', get: r => r.oppAdv.opp_tov, fmt: (v, r) => f1(v) + rk(r.ranks, 'opp_tov')},
      A('drb', 'DRB%'),
      {k: 'opp_ftr', t: 'Soup. FT rate', get: r => r.oppAdv.opp_ftr, fmt: (v, r) => f1(v) + rk(r.ranks, 'opp_ftr'), asc: true}],
    shoot: [team, A('fg', 'FG%', {rk: '-'}), A('two', '2P%'), A('three', '3P%'), A('ft', 'TH%'), A('three_par', '3PA podíl'),
      {k: 'fta_rate', t: 'FTA/FGA', get: r => r.adv.fta_rate, fmt: f1}, A('ast_pct', 'AST%'), A('ast_to', 'AST/TO', {f: v => v == null ? '—' : v.toFixed(2)}),
      A('stl_pct', 'STL%'), A('blk_pct', 'BLK%'),
      {k: 'opp_three', t: 'Soup. 3P%', get: r => r.oppAdv.opp_three, fmt: (v, r) => f1(v) + rk(r.ranks, 'opp_three'), asc: true}],
    box: [team].concat(['pts', 'reb', 'oreb', 'ast', 'to', 'stl', 'blk', 'paint', 'fast', 'second', 'bench', 'offto'].map(k =>
      ({k, t: {pts: 'Body', reb: 'Doskoky', oreb: 'Útoč. d.', ast: 'Asist.', to: 'Ztráty', stl: 'Zisky', blk: 'Bloky', paint: 'Paint', fast: 'Protiút.', second: '2. šance', bench: 'Lavička', offto: 'Po ztrátách'}[k],
        get: r => r.perGame[k], fmt: f1, asc: k === 'to'}))),
    misc: [team,
      {k: 'cnet', t: 'Clutch +/−', get: r => r.clutch.net, fmt: signed, cls: cls, title: 'posledních 5 min, rozdíl ≤ 5'},
      {k: 'cwl', t: 'Clutch V-P', get: r => r.clutch.w, fmt: (v, r) => r.clutch.w + '-' + r.clutch.l},
      {k: 'cfg', t: 'Clutch FG%', get: r => r.clutch.fgPct, fmt: f1},
      {k: 'avgSec', t: 'Ø s útoku', get: r => r.attack.avgSec, fmt: f1, asc: true, title: 'průměrná sekunda útoku, ve které tým skóroval'},
      {k: 'ppp', t: 'Body/útok', get: r => r.attack.ptsPerPoss, fmt: v => v == null ? '—' : v.toFixed(2)}]
      .concat(['0-5', '5-10', '10-15', '15-20', '20+'].map((b, i) => ({k: 'b' + i, t: b + ' s', get: r => {
        const tot = r.attack.pts.reduce((x, y) => x + y, 0); return tot ? 100 * r.attack.pts[i] / tot : null; }, fmt: v => f0(v) + ' %', title: 'podíl bodů'}))),
  };
  const notes = {
    adv: 'ORtg/DRtg = body na 100 držení, držení = FGA − ORB + TO + 0,44·FTA. Pace = držení na 40 minut.',
    ff: 'Four factors (Dean Oliver): eFG% = (FGM + 0,5·3PM)/FGA, TOV% = TO/(FGA + 0,44·FTA + TO), ORB% = ORB/(ORB + DRB soupeře), FT rate = FTM/FGA.',
    shoot: 'AST% = podíl asistovaných košů, STL% = zisky na 100 držení soupeře, BLK% = bloky na 100 dvojkových pokusů soupeře.',
    box: 'Průměry na zápas.',
    misc: 'Clutch = posledních 5 minut 4. čtvrtiny / prodloužení při rozdílu nejvýš 5 bodů. Čas útoku = rekonstrukce držení z play-by-play (odhad, hodiny mají rozlišení 1 s).',
  };
  const draw = () => {
    const a = avg.adv || {}, pg = avg.perGame || {};
    const foot = `<tfoot><tr class="avg">${sets[mode].map((c, i) => {
      if (i === 0) return '<td class="l">Průměr ligy</td>';
      const v = mode === 'box' ? pg[c.k] : a[c.k];
      return `<td>${v == null ? '' : (c.k === 'ast_to' ? v.toFixed(2) : f1(v))}</td>`;
    }).join('')}</tr></tfoot>`;
    sortTable($('#lt'), sets[mode], T, {sort: mode === 'adv' ? 'net' : null, stickyFirst: true, foot});
    $('#lnote').textContent = notes[mode];
  };
  $('#modes').querySelectorAll('button').forEach(b => b.onclick = () => {
    mode = b.dataset.m; $('#modes').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); draw();
  });
  draw();
}

/* ---------------- HRÁČI ---------------- */
async function viewPlayers(app) {
  const pl = (await getJSON('players.json')).players;
  const teams = Object.keys(TEAMS).sort((a, b) => label(a).localeCompare(label(b), 'cs'));
  let mode = 'pg';
  app.innerHTML = `<h1>Hráči</h1><div class="toolbar" style="margin-top:14px">
    <input type="search" id="q" placeholder="Hledat hráče…">
    <select id="team"><option value="">Všechny týmy</option>${teams.map(s => `<option value="${s}">${esc(TEAMS[s].name)}</option>`).join('')}</select>
    <select id="minmin"><option value="0">Všichni</option><option value="10" selected>≥ 10 min/zápas</option><option value="20">≥ 20 min/zápas</option></select></div>
    <div class="tabs" id="modes"><button data-m="pg" class="on">Na zápas</button><button data-m="adv">Pokročilé</button><button data-m="tot">Součty</button><button data-m="p40">Na 40 min</button></div>
    <div id="pt"></div><div class="caption">TS% = body / (2·(FGA + 0,44·FTA)), USG% = podíl akcí týmu zakončených hráčem, když hrál. On/off = net rating týmu s hráčem na hřišti minus bez něj. EFF = body + doskoky + asistence + zisky + bloky − neproměněné střely − ztráty.</div>`;
  const name = {k: 'name', t: 'Hráč', l: true, get: r => r.name, fmt: (v, r) => `<span class="name">${esc(v)}</span> <a class="muted" href="#/tym/${r.team}">${esc(r.teamLabel)}</a>`, asc: true};
  const gp = {k: 'gp', t: 'Z', get: r => r.gp};
  const P = (k, t, o = {}) => ({k, t, get: r => r.perGame[k], fmt: f1, ...o});
  const sets = {
    pg: [name, gp, P('min', 'Min'), P('pts', 'Body'), P('reb', 'Dosk.'), P('oreb', 'Út.d.'), P('ast', 'Asist.'), P('stl', 'Zisky'), P('blk', 'Bloky'), P('to', 'Ztráty', {asc: true}),
      P('tpm', '3PM'), {k: 'fg', t: 'FG%', get: r => r.fg, fmt: f1}, {k: 'three', t: '3P%', get: r => r.three, fmt: f1}, {k: 'ft', t: 'TH%', get: r => r.ft, fmt: f1}, P('eff', 'EFF')],
    adv: [name, gp, P('min', 'Min'), {k: 'ts', t: 'TS%', get: r => r.ts, fmt: f1}, {k: 'efg', t: 'eFG%', get: r => r.efg, fmt: f1},
      {k: 'usg', t: 'USG%', get: r => r.usg, fmt: f1}, {k: 'astTo', t: 'AST/TO', get: r => r.astTo, fmt: v => v == null ? '—' : v.toFixed(2)},
      P('gmsc', 'GmSc'), {k: 'pm', t: '+/−', get: r => r.pm, fmt: signed, cls: cls}, {k: 'pm40', t: '±/40', get: r => r.pm40, fmt: signed, cls: cls},
      {k: 'onnet', t: 'Net s ním', get: r => r.on.net, fmt: signed, cls: cls}, {k: 'offnet', t: 'Net bez', get: r => r.off.net, fmt: signed, cls: cls},
      {k: 'onOff', t: 'On/off', get: r => r.onOff, fmt: v => `<b>${signed(v)}</b>`, cls: cls}, {k: 'dd', t: 'DD', get: r => r.dd}, {k: 'high', t: 'Max', get: r => r.high}],
    tot: [name, gp, {k: 'gs', t: 'Start', get: r => r.gs}, {k: 'min', t: 'Min', get: r => r.min, fmt: f0}].concat(
      ['pts', 'reb', 'ast', 'stl', 'blk', 'to', 'pf', 'foulon', 'paint', 'fast'].map(k => ({k: 't' + k, t: {pts: 'Body', reb: 'Dosk.', ast: 'Asist.', stl: 'Zisky', blk: 'Bloky', to: 'Ztráty', pf: 'Fauly', foulon: 'Fauly na', paint: 'Paint', fast: 'Protiút.'}[k], get: r => r.totals[k]})),
      [{k: 'fgt', t: 'FG', get: r => r.totals.fga, fmt: (v, r) => r.totals.fgm + '/' + r.totals.fga}, {k: 'tpt', t: '3P', get: r => r.totals.tpa, fmt: (v, r) => r.totals.tpm + '/' + r.totals.tpa},
        {k: 'ftt', t: 'TH', get: r => r.totals.fta, fmt: (v, r) => r.totals.ftm + '/' + r.totals.fta}]),
    p40: [name, gp, P('min', 'Min')].concat(['pts', 'reb', 'ast', 'stl', 'blk', 'to'].map(k => ({k: 'x' + k, t: {pts: 'Body', reb: 'Dosk.', ast: 'Asist.', stl: 'Zisky', blk: 'Bloky', to: 'Ztráty'}[k] + '/40', get: r => r.per40[k], fmt: f1}))),
  };
  const sortKey = {pg: 'pts', adv: 'ts', tot: 'tpts', p40: 'xpts'};
  const draw = () => {
    const q = $('#q').value.trim().toLowerCase(), t = $('#team').value, mm = +$('#minmin').value;
    const rows = pl.filter(p => (!q || p.name.toLowerCase().includes(q)) && (!t || p.team === t) && (p.perGame.min || 0) >= mm);
    sortTable($('#pt'), sets[mode], rows, {sort: sortKey[mode], stickyFirst: true});
  };
  $('#q').oninput = draw; $('#team').onchange = draw; $('#minmin').onchange = draw;
  $('#modes').querySelectorAll('button').forEach(b => b.onclick = () => {
    mode = b.dataset.m; $('#modes').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); draw();
  });
  draw();
}

/* ---------------- ŽEBŘÍČKY ---------------- */
async function viewLeaders(app) {
  const L = await getJSON('leaders.json');
  const keys = Object.keys(L).filter(k => L[k] && L[k].rows);
  app.innerHTML = `<h1>Žebříčky</h1><p class="muted">Průměry vyžadují aspoň ${L.minGames} odehraných zápasů; procenta navíc minimální počet pokusů na zápas (TS/eFG 5 FGA, 3P% 2 pokusy, TH% 2 pokusy), USG a on/off 15 minut na zápas.</p>
    <div class="grid g3">${keys.map(k => leaderCard(L[k], 10)).join('')}</div>`;
}

/* ---------------- TÝM ---------------- */
async function viewTeam(app, slug) {
  const [t, lg] = await Promise.all([getJSON('teams/' + slug + '.json'), getJSON('league.json')]);
  const avg = (lg.averages || {}).adv || {};
  const s = t.standing || {};
  const R = t.ranks || {};
  const stat = (v, cap, k, c) => `<div class="stat"><b class="${c || ''}">${v}${k ? rk(R, k) : ''}</b><span>${cap}</span></div>`;
  app.innerHTML = `
    <div class="team-hero">${t.logo ? `<img src="${esc(t.logo)}" alt="" onerror="this.remove()">` : ''}<div><div class="eyebrow">${s.pos ? s.pos + '. místo' : ''} · trenér ${esc(t.coach || '—')}</div><h1>${esc(t.name)}</h1>
      <div class="muted">${s.w}-${s.l} · skóre ${s.pf}:${s.pa} · doma ${s.home} · venku ${s.away} · série ${s.streak || '—'}</div></div></div>
    <section><div class="stats">
      ${stat(f1(t.adv.ortg), 'Útočný rating (ORtg)', 'ortg')}${stat(f1(t.adv.drtg), 'Obranný rating (DRtg)', 'drtg')}
      ${stat(signed(t.adv.net), 'Net rating', 'net', cls(t.adv.net))}${stat(f1(t.adv.pace), 'Pace (držení/40 min)', 'pace')}
      ${stat(f1(t.perGame.ppg), 'Body na zápas', 'ppg')}${stat(f1(t.perGame.oppg), 'Obdržené na zápas', 'oppg')}
      ${stat(f1(t.adv.ts), 'TS%', 'ts')}${stat(signed(t.clutch.net), `Clutch +/− (${t.clutch.w}-${t.clutch.l})`, null, cls(t.clutch.net))}
    </div></section>
    <div class="grid g2">
      <section class="panel"><h2>Four factors vs. průměr ligy</h2><div class="cmp" id="ff"></div></section>
      <section class="panel"><h2>Čtvrtiny (průměr na zápas)</h2><div id="qt"></div>
        <h3 style="margin-top:16px">Průběh</h3><div class="muted" style="font-size:.85rem">Největší vedení ${t.flow.biggestLead} · největší manko ${t.flow.biggestDeficit} · nejdelší série ${t.flow.biggestRun}:0 (soupeř ${t.flow.biggestRunAllowed}:0) · ${f1(t.flow.leadChangesPerGame)} střídání vedení na zápas</div></section>
    </div>
    <section style="margin-top:16px"><h2>Hráči</h2><div id="pl"></div></section>
    <div class="grid g2">
      <section class="panel"><h2>Zóny střelby</h2><div id="zones"></div></section>
      <section class="panel"><h2>Body podle času útoku</h2><div id="att"></div></section>
    </div>
    <section><h2>Sestavy</h2><div class="tabs" id="lu"><button data-s="fives" class="on">Pětky (≥ 5 min)</button><button data-s="trios">Trojice (≥ 10 min)</button><button data-s="pairs">Dvojice (≥ 15 min)</button></div><div id="lut"></div>
      <div class="caption">Rekonstrukce z play-by-play podle střídání. Net = rozdíl útočného a obranného ratingu na 100 držení, když byla sestava spolu na hřišti.</div></section>
    <div class="grid g2">
      <section><h2>Asistenční dvojice</h2><div id="ast"></div></section>
      <section><h2>Zápasy</h2><div id="log"></div></section>
    </div>`;
  // four factors
  const ff = [['eFG%', t.adv.efg, avg.efg, true], ['TOV%', t.adv.tov, avg.tov, false], ['ORB%', t.adv.orb, avg.orb, true], ['FT rate', t.adv.ftr, avg.ftr, true],
    ['Soupeř eFG%', t.oppAdv.opp_efg, avg.efg, false], ['Soupeř TOV%', t.oppAdv.opp_tov, avg.tov, true], ['DRB%', t.adv.drb, avg.drb, true], ['Soupeř FT rate', t.oppAdv.opp_ftr, avg.ftr, false]];
  $('#ff').innerHTML = ff.map(([l, v, a, hi]) => {
    const mx = Math.max(v || 0, a || 0, 1), good = hi ? v >= a : v <= a;
    return `<div><div class="lbl"><span>${l}</span><span class="${good ? 'pos' : 'neg'}">${signed(v != null && a != null ? Math.round((v - a) * 10) / 10 : null)}</span></div>
      <div class="row"><span class="who">${esc(t.label)}</span><div class="track"><div class="fill h" style="width:${100 * (v || 0) / mx}%"></div></div><span class="v">${f1(v)}</span></div>
      <div class="row"><span class="who">liga</span><div class="track"><div class="fill lg" style="width:${100 * (a || 0) / mx}%"></div></div><span class="v">${f1(a)}</span></div></div>`;
  }).join('');
  sortTable($('#qt'), [{k: 'label', t: 'Perioda', l: true, get: r => r.label, s: false}, {k: 'ppg', t: 'Body', get: r => r.ppg, fmt: f1, s: false},
    {k: 'oppg', t: 'Obdr.', get: r => r.oppg, fmt: f1, s: false}, {k: 'diff', t: '+/−', get: r => r.diff, fmt: signed, cls: cls, s: false}, {k: 'n', t: 'Zápasů', get: r => r.n, s: false}], t.quarters);
  // hráči
  sortTable($('#pl'), [
    {k: 'name', t: 'Hráč', l: true, get: r => r.name, fmt: (v, r) => `<span class="muted">${esc(r.shirt)}</span> <span class="name">${esc(v)}</span>`, asc: true},
    {k: 'gp', t: 'Z', get: r => r.gp}, {k: 'min', t: 'Min', get: r => r.perGame.min, fmt: f1}, {k: 'pts', t: 'Body', get: r => r.perGame.pts, fmt: f1},
    {k: 'reb', t: 'Dosk.', get: r => r.perGame.reb, fmt: f1}, {k: 'ast', t: 'Asist.', get: r => r.perGame.ast, fmt: f1},
    {k: 'stl', t: 'Zisky', get: r => r.perGame.stl, fmt: f1}, {k: 'to', t: 'Ztr.', get: r => r.perGame.to, fmt: f1, asc: true},
    {k: 'ts', t: 'TS%', get: r => r.ts, fmt: f1}, {k: 'efg', t: 'eFG%', get: r => r.efg, fmt: f1}, {k: 'three', t: '3P%', get: r => r.three, fmt: (v, r) => f1(v) + ` <span class="muted">${r.totals.tpm}/${r.totals.tpa}</span>`},
    {k: 'usg', t: 'USG%', get: r => r.usg, fmt: f1}, {k: 'eff', t: 'EFF', get: r => r.perGame.eff, fmt: f1},
    {k: 'pm', t: '+/−', get: r => r.pm, fmt: signed, cls: cls}, {k: 'onOff', t: 'On/off', get: r => r.onOff, fmt: signed, cls: cls}], t.players, {sort: 'pts', stickyFirst: true});
  // zóny
  const ZL = {paint: 'Dvojka v paintu', mid: 'Střední dvojka', corner3: 'Trojka z rohu', above3: 'Trojka z oblouku'};
  $('#zones').innerHTML = `<div class="tx"><table><thead><tr><th class="l">Zóna</th><th>Tým</th><th>%</th><th>Podíl</th><th>Soupeři</th><th>%</th></tr></thead><tbody>${Object.keys(ZL).map(z => {
    const a = t.zones[z], o = t.oppZones[z];
    return `<tr><td class="l">${ZL[z]}</td><td>${a.m}/${a.a}</td><td>${f1(a.pct)}</td><td>${f0(a.share)} %</td><td>${o.m}/${o.a}</td><td>${f1(o.pct)}</td></tr>`;
  }).join('')}</tbody></table></div>`;
  attackTable($('#att'), t.attack.bands, [{name: 'Tým', bands: t.attack.pts}], `Útoků ~${t.attack.possessions}, ${t.attack.ptsPerPoss == null ? '—' : t.attack.ptsPerPoss.toFixed(2)} bodu na útok, Ø sekunda skórování ${f1(t.attack.avgSec)} s.`);
  // sestavy
  const luDraw = size => sortTable($('#lut'), [
    {k: 'players', t: 'Hráči', l: true, get: r => r.players.join(', '), fmt: v => `<span style="white-space:normal">${esc(v)}</span>`, s: false},
    {k: 'min', t: 'Min', get: r => r.min, fmt: f1}, {k: 'sc', t: 'Skóre', get: r => r.pf, fmt: (v, r) => r.pf + ':' + r.pa},
    {k: 'pm', t: '+/−', get: r => r.pm, fmt: signed, cls: cls}, {k: 'ortg', t: 'ORtg', get: r => r.ortg, fmt: f1}, {k: 'drtg', t: 'DRtg', get: r => r.drtg, fmt: f1, asc: true},
    {k: 'net', t: 'Net', get: r => r.net, fmt: v => `<b>${signed(v)}</b>`, cls: cls}, {k: 'efg', t: 'eFG my/soup.', get: r => r.efg, fmt: (v, r) => f0(r.efg) + ' / ' + f0(r.oefg)}],
    t.lineups[size].slice(0, 40), {sort: 'min'});
  $('#lu').querySelectorAll('button').forEach(b => b.onclick = () => { $('#lu').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); luDraw(b.dataset.s); });
  luDraw('fives');
  sortTable($('#ast'), [{k: 'p', t: 'Nahrávač → střelec', l: true, get: r => r.passer, fmt: (v, r) => esc(r.passer) + ' → ' + esc(r.scorer), s: false},
    {k: 'ast', t: 'Asist.', get: r => r.ast}, {k: 'pts', t: 'Body', get: r => r.pts}], t.assistPairs.slice(0, 15), {sort: 'ast'});
  sortTable($('#log'), [
    {k: 'date', t: 'Datum', l: true, get: r => r.date, fmt: (v, r) => `<a href="#/zapas/${r.fibaId}">${v ? v.split('-').reverse().slice(0, 2).join('. ') + '.' : ''}</a>`, asc: true},
    {k: 'opp', t: 'Soupeř', l: true, get: r => r.opponentLabel, fmt: (v, r) => (r.venue === 'home' ? 'vs ' : '@ ') + esc(v), asc: true},
    {k: 'res', t: '', get: r => r.result, s: false, fmt: v => `<span class="badge ${v === 'W' ? 'w' : 'l'}">${v === 'W' ? 'V' : 'P'}</span>`},
    {k: 'sc', t: 'Skóre', get: r => r.score[0] - r.score[1], fmt: (v, r) => r.score.join(':') + (r.ot ? ' pp' : '')},
    {k: 'net', t: 'Net', get: r => r.net, fmt: signed, cls: cls}, {k: 'pace', t: 'Pace', get: r => r.pace, fmt: f1}, {k: 'efg', t: 'eFG%', get: r => r.efg, fmt: f1},
    {k: 'top', t: 'Nejlepší střelec', l: true, get: r => r.topScorer, s: false}], t.log.slice().reverse());
}

function attackTable(el, bands, rows, note) {
  const mx = Math.max(1, ...rows.flatMap(r => r.bands));
  el.innerHTML = `<div class="tx"><table class="heat"><thead><tr><th class="l"></th>${bands.map(b => `<th>${b} s</th>`).join('')}<th>Celkem</th></tr></thead><tbody>${rows.map(r =>
    `<tr><td class="l name">${esc(r.name)}</td>${r.bands.map(v => `<td class="h" style="background:color-mix(in srgb,var(--home) ${Math.round(8 + 60 * v / mx)}%,var(--panel));${v / mx > .55 ? 'color:#2b2b2b;font-weight:600' : ''}">${v}</td>`).join('')}<td><b>${r.bands.reduce((a, b) => a + b, 0)}</b></td></tr>`).join('')}</tbody></table></div>
    <div class="caption">${note}</div>`;
}

/* ---------------- ZÁPAS ---------------- */
async function viewMatch(app, fid) {
  const sch = await getJSON('schedule.json');
  const fx = sch.fixtures.find(f => String(f.fibaId) === fid) || {};
  let g = null;
  try { g = await getJSON('matches/' + fid + '.json'); } catch (e) { /* zatím jen živě */ }
  const start = fx.datetime ? new Date(fx.datetime).getTime() : 0;
  const maybeLive = (!g || g.status !== 'final') && Date.now() > start - 30 * 60e3 && Date.now() < start + 4 * 3600e3;
  if (maybeLive) {
    const lg = await getLive(fid);
    if (lg) g = lg;
  }
  if (!g) { app.innerHTML = `<div class="err">Zápas ${esc(fid)} zatím nemá statistiky${fx.datetime ? ' (začátek ' + fmtDate(fx.datetime) + ')' : ''}.</div>`; return; }
  renderMatch(app, g, fx);
  if (g.status !== 'final' && maybeLive) {
    liveTimer = setInterval(async () => {
      const lg = await getLive(fid);
      if (lg && lg.updatedAt !== g.updatedAt) { g = lg; renderMatch(app, g, fx, true); }
    }, LIVE_POLL_MS);
  }
}

let MT = {side: 'home', lu: 'fives'};
function renderMatch(app, g, fx, keepScroll) {
  const H = g.home, A = g.away;
  const live = g.status === 'live';
  const st = live ? `<span class="badge live">živě</span> ${esc(g.periodLabel)} · ${esc(g.clock)}${g.updatedAt ? ' · aktualizace ' + new Date(g.updatedAt).toLocaleTimeString('cs-CZ') : ''}`
    : g.status === 'final' ? 'Konec' + (g.period > 4 ? ' po prodloužení' : '') : 'Před zápasem';
  const y = window.scrollY;
  app.innerHTML = `
    <div class="score-hero">
      <div class="side"><img src="${esc(H.logo || '')}" alt="" onerror="this.remove()"><div><div class="nm"><a class="team-link" href="#/tym/${H.slug}">${esc(H.name)}</a></div><div class="muted">${esc(H.coach || '')}</div></div></div>
      <div><div class="sc"><span class="h">${H.score}</span> : <span class="a">${A.score}</span></div><div class="st">${st}</div>
        <div class="st">${esc((g.fixture || fx || {}).round || '')} · ${fmtDate((g.fixture || fx || {}).datetime)}${g.attendance ? ' · ' + g.attendance + ' diváků' : ''}</div></div>
      <div class="side r"><div><div class="nm"><a class="team-link" href="#/tym/${A.slug}">${esc(A.name)}</a></div><div class="muted">${esc(A.coach || '')}</div></div><img src="${esc(A.logo || '')}" alt="" onerror="this.remove()"></div>
    </div>
    ${live && g.live ? liveBlock(g) : ''}
    <section style="margin-top:16px"><div class="grid g2">
      <div class="panel"><h2>Skóre po čtvrtinách</h2><div id="qt"></div></div>
      <div class="panel"><h2>Průběh zápasu</h2>${leadChart(g)}<div class="caption">Rozdíl skóre (nad osou vede ${esc(H.label)}). ${g.flow.leadChanges}× střídání vedení, ${g.flow.ties}× vyrovnáno. Největší vedení ${esc(H.label)} +${H.lead.max}, ${esc(A.label)} +${A.lead.max}.</div></div>
    </div></section>
    <section><div class="grid g2">
      <div class="panel"><h2>Four factors & ratingy</h2><div class="cmp">${cmpRows(g)}</div><div class="caption">Držení ${f1(H.adv.poss)} / ${f1(A.adv.poss)}, pace ${f1(g.pace)}. ORtg = body na 100 držení.</div></div>
      <div class="panel"><h2>Body podle typu</h2><div class="cmp">${cmpBox(g)}</div>
        ${g.flow.runs.length ? `<h3 style="margin-top:16px">Série bez odpovědi</h3><div style="font-size:.85rem">${g.flow.runs.map(r => `<div><span class="dot ${r.team === 'home' ? 'h' : 'a'}"></span><b>${r.pts}:0</b> ${esc(g[r.team].label)} · ${esc(r.start)} – ${esc(r.end)} <span class="muted">(${r.from.join(':')} → ${r.to.join(':')})</span></div>`).join('')}</div>` : ''}
        ${clutchLine(g)}</div>
    </div></section>
    <section><div class="tabs" id="side"><button data-s="home" class="${MT.side === 'home' ? 'on' : ''}">${esc(H.label)}</button><button data-s="away" class="${MT.side === 'away' ? 'on away' : ''}">${esc(A.label)}</button></div>
      <h2>Box score</h2><div id="box"></div>
      <div class="grid g2" style="margin-top:16px">
        <div class="panel"><h2>Střely</h2><div id="shots"></div></div>
        <div class="panel"><h2>Body podle času útoku</h2><div id="att"></div></div>
      </div>
      <h2 style="margin-top:16px">Sestavy</h2><div class="tabs" id="lu"><button data-s="fives">Pětky</button><button data-s="trios">Trojice</button><button data-s="pairs">Dvojice</button></div><div id="lut"></div>
      <h2 style="margin-top:16px">Asistenční dvojice</h2><div id="ast"></div>
    </section>`;
  sortTable($('#qt'), [{k: 't', t: '', l: true, get: r => r.t, s: false}].concat(g.quarters.map((q, i) => ({k: 'q' + i, t: q.label, get: r => r.q[i], s: false})),
    [{k: 'tot', t: 'Celkem', get: r => r.tot, s: false, fmt: v => `<b>${v}</b>`}]),
    [{t: H.label, q: g.quarters.map(q => q.home), tot: H.score}, {t: A.label, q: g.quarters.map(q => q.away), tot: A.score}]);
  const sideBtns = $('#side').querySelectorAll('button');
  sideBtns.forEach(b => b.onclick = () => { MT.side = b.dataset.s; sideBtns.forEach(x => x.classList.remove('on', 'away')); b.classList.add('on'); if (MT.side === 'away') b.classList.add('away'); drawSide(g); });
  $('#lu').querySelectorAll('button').forEach(b => { b.classList.toggle('on', b.dataset.s === MT.lu); b.onclick = () => { MT.lu = b.dataset.s; $('#lu').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); drawLineups(g); }; });
  drawSide(g);
  if (keepScroll) window.scrollTo(0, y);
}

function liveBlock(g) {
  const L = g.live;
  const oc = s => (L.onCourt[s] || []).map(p => `<span>#${esc(p.shirt)} ${esc(p.name)}</span>`).join('');
  const ft = s => (L.foulTrouble[s] || []).map(p => `${esc(p.name)} (${p.pf})`).join(', ') || '—';
  return `<section class="panel" style="margin-top:16px;border-color:var(--bad)"><h2><span class="badge live">živě</span> Teď na hřišti</h2>
    <div class="grid g2">
      <div><div class="eyebrow"><span class="dot h"></span>${esc(g.home.label)} · týmové fauly ${L.teamFoulsPeriod.home} · oddechy ${L.timeoutsUsed.home}</div><div class="oncourt" style="margin-top:6px">${oc('home')}</div><div class="caption">Faulové potíže: ${ft('home')}</div></div>
      <div><div class="eyebrow"><span class="dot a"></span>${esc(g.away.label)} · týmové fauly ${L.teamFoulsPeriod.away} · oddechy ${L.timeoutsUsed.away}</div><div class="oncourt" style="margin-top:6px">${oc('away')}</div><div class="caption">Faulové potíže: ${ft('away')}</div></div>
    </div>
    <div class="caption">${L.currentRun ? `Aktuální série: <b>${esc(g[L.currentRun.team].label)} ${L.currentRun.pts}:0</b> od ${esc(L.currentRun.since)}. ` : ''}Posledních 5 minut: ${signed(L.last5min.margin)} pro ${esc(L.last5min.margin >= 0 ? g.home.label : g.away.label)}.</div></section>`;
}

function cmpBar(lbl, hv, av, hi, fmt = f1) {
  const mx = Math.max(Math.abs(hv || 0), Math.abs(av || 0), 1e-9);
  const hB = hi ? hv >= av : hv <= av;
  return `<div><div class="lbl"><span>${lbl}</span></div>
    <div class="row"><span class="who"><span class="dot h"></span></span><div class="track"><div class="fill h" style="width:${100 * Math.max(0, hv || 0) / mx}%"></div></div><span class="v ${hB ? 'pos' : ''}">${fmt(hv)}</span></div>
    <div class="row"><span class="who"><span class="dot a"></span></span><div class="track"><div class="fill a" style="width:${100 * Math.max(0, av || 0) / mx}%"></div></div><span class="v ${!hB ? 'pos' : ''}">${fmt(av)}</span></div></div>`;
}
function cmpRows(g) {
  const h = g.home.adv, a = g.away.adv;
  return [['ORtg (body na 100 držení)', 'ortg', true], ['eFG %', 'efg', true], ['TOV % (ztrátovost)', 'tov', false], ['ORB % (útočné doskoky)', 'orb', true], ['FT rate (FTM/FGA)', 'ftr', true], ['TS %', 'ts', true]]
    .map(([l, k, hi]) => cmpBar(l, h[k], a[k], hi)).join('');
}
function cmpBox(g) {
  const h = g.home.box, a = g.away.box;
  return [['Body v paintu', 'paint'], ['Rychlé protiútoky', 'fast'], ['Druhé šance', 'second'], ['Po ztrátách soupeře', 'offto'], ['Lavička', 'bench'], ['Asistence', 'ast']]
    .map(([l, k]) => cmpBar(l, h[k], a[k], true, f0)).join('');
}
function clutchLine(g) {
  const h = g.home.clutch, a = g.away.clutch;
  if (!(h.fga + h.fta + a.fga + a.fta)) return '';
  const who = c => c.players.slice(0, 3).map(p => esc(p.name) + ' ' + p.pts).join(', ');
  return `<h3 style="margin-top:16px">Clutch (posl. 5 min, rozdíl ≤ 5)</h3><div style="font-size:.85rem">
    <div><span class="dot h"></span>${h.pts} b. · FG ${h.fgm}/${h.fga} · TH ${h.ftm}/${h.fta} · ztráty ${h.to} ${h.players.length ? '· ' + who(h) : ''}</div>
    <div><span class="dot a"></span>${a.pts} b. · FG ${a.fgm}/${a.fga} · TH ${a.ftm}/${a.fta} · ztráty ${a.to} ${a.players.length ? '· ' + who(a) : ''}</div></div>`;
}

function leadChart(g) {
  const tl = g.flow.timeline, W = 600, Hh = 170, pl = 30, pr = 6, pt = 8, pb = 18;
  const total = Math.max(g.minutes * 60, tl.length ? tl[tl.length - 1][0] : 1, 1);
  let m = 6; tl.forEach(p => m = Math.max(m, Math.abs(p[1])));
  const X = el => pl + (W - pl - pr) * el / total, Y = v => pt + (Hh - pt - pb) * (0.5 - 0.5 * v / m);
  let path = `M${X(0)},${Y(0)}`, py = Y(0);
  for (const [el, v] of tl) { path += ` L${X(el).toFixed(1)},${py.toFixed(1)} L${X(el).toFixed(1)},${Y(v).toFixed(1)}`; py = Y(v); }
  path += ` L${X(total)},${py.toFixed(1)}`;
  const area = (sign) => { let d = `M${X(0)},${Y(0)}`, yy = Y(0); for (const [el, v] of tl) { const vv = sign > 0 ? Math.max(0, v) : Math.min(0, v); d += ` L${X(el).toFixed(1)},${yy.toFixed(1)} L${X(el).toFixed(1)},${Y(vv).toFixed(1)}`; yy = Y(vv); } return d + ` L${X(total)},${yy.toFixed(1)} L${X(total)},${Y(0)} Z`; };
  const qs = []; for (let s = 600, i = 1; s < total; s += (i < 4 ? 600 : 300), i++) qs.push(s);
  return `<svg class="chart" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Průběh rozdílu skóre">
    ${qs.map(s => `<line x1="${X(s)}" x2="${X(s)}" y1="${pt}" y2="${Hh - pb}" stroke="#525048"/>`).join('')}
    <line x1="${pl}" x2="${W - pr}" y1="${Y(0)}" y2="${Y(0)}" stroke="#6f6e66"/>
    <path d="${area(1)}" fill="rgba(255,211,26,.28)"/><path d="${area(-1)}" fill="rgba(159,180,199,.28)"/>
    <path d="${path}" fill="none" stroke="#f5f5f2" stroke-width="1.4"/>
    <text x="2" y="${Y(m) + 8}">+${m}</text><text x="2" y="${Y(-m)}">−${m}</text>
    ${g.quarters.map((q, i) => { const s0 = i < 4 ? i * 600 : 2400 + (i - 4) * 300, s1 = i < 4 ? s0 + 600 : s0 + 300; return `<text x="${(X(s0) + X(Math.min(s1, total))) / 2 - 8}" y="${Hh - 4}">${q.label}</text>`; }).join('')}
  </svg>`;
}

function drawSide(g) {
  const T = g[MT.side];
  const col = MT.side === 'home' ? 'var(--home)' : 'var(--away)';
  const tot = T.box;
  sortTable($('#box'), [
    {k: 'name', t: 'Hráč', l: true, get: r => r.name, asc: true, fmt: (v, r) => `<span class="muted">${esc(r.shirt)}</span> <span class="name">${esc(v)}</span>${r.starter ? ' <span class="badge">S</span>' : ''}`},
    {k: 'min', t: 'Min', get: r => r.min, fmt: f1}, {k: 'pts', t: 'Body', get: r => r.pts, fmt: v => `<b>${v}</b>`},
    {k: 'fg', t: 'FG', get: r => r.fga, fmt: (v, r) => r.fgm + '/' + r.fga}, {k: 'tp', t: '3P', get: r => r.tpa, fmt: (v, r) => r.tpm + '/' + r.tpa},
    {k: 'ft', t: 'TH', get: r => r.fta, fmt: (v, r) => r.ftm + '/' + r.fta},
    {k: 'reb', t: 'Dosk.', get: r => r.reb, fmt: (v, r) => v + ` <span class="muted">${r.oreb}/${r.dreb}</span>`},
    {k: 'ast', t: 'As', get: r => r.ast}, {k: 'stl', t: 'Zi', get: r => r.stl}, {k: 'blk', t: 'Bl', get: r => r.blk}, {k: 'to', t: 'Zt', get: r => r.to, asc: true},
    {k: 'pf', t: 'Fa', get: r => r.pf}, {k: 'ts', t: 'TS%', get: r => r.ts, fmt: f0}, {k: 'usg', t: 'USG%', get: r => r.usg, fmt: f0},
    {k: 'eff', t: 'EFF', get: r => r.eff}, {k: 'gmsc', t: 'GmSc', get: r => r.gmsc, fmt: f1},
    {k: 'pm', t: '+/−', get: r => r.pm, fmt: signed, cls: cls}, {k: 'onOff', t: 'On/off', get: r => r.onOff, fmt: signed, cls: cls, title: 'net rating s hráčem minus bez něj'}],
    T.players, {sort: 'pts', stickyFirst: true,
      foot: `<tfoot><tr class="tot"><td class="l sticky">Tým</td><td></td><td>${tot.pts}</td><td>${tot.fgm}/${tot.fga}</td><td>${tot.tpm}/${tot.tpa}</td><td>${tot.ftm}/${tot.fta}</td><td>${tot.reb} <span class="muted">${tot.oreb}/${tot.dreb}</span></td><td>${tot.ast}</td><td>${tot.stl}</td><td>${tot.blk}</td><td>${tot.to}</td><td>${tot.pf}</td><td>${f0(T.adv.ts)}</td><td></td><td></td><td></td><td></td><td></td></tr></tfoot>`});
  // střely
  const ZL = {paint: 'Dvojka v paintu', mid: 'Střední dvojka', corner3: 'Trojka z rohu', above3: 'Trojka z oblouku'};
  $('#shots').innerHTML = shotChart(T.shots, col) + `<div class="tx"><table style="margin-top:8px">${Object.keys(ZL).map(z => {
    const v = T.zones[z]; return `<tr><td class="l">${ZL[z]}</td><td>${v.m}/${v.a}</td><td>${f0(v.pct)} %</td></tr>`; }).join('')}</table></div>`;
  attackTable($('#att'), T.attack.bands, T.attack.players.map(p => ({name: p.name, bands: p.bands})).concat([{name: 'Tým', bands: T.attack.team}]),
    `Útoků ~${T.attack.possessions}, ${T.attack.ptsPerPoss == null ? '—' : T.attack.ptsPerPoss.toFixed(2)} bodu na útok, Ø sekunda skórování ${f1(T.attack.avgSec)} s. Odhad z play-by-play.`);
  drawLineups(g);
  sortTable($('#ast'), [{k: 'p', t: 'Nahrávač → střelec', l: true, get: r => r.passer, fmt: (v, r) => esc(r.passer) + ' → ' + esc(r.scorer), s: false},
    {k: 'ast', t: 'Asist.', get: r => r.ast}, {k: 'pts', t: 'Body', get: r => r.pts}], T.assistPairs, {sort: 'ast'});
}
function drawLineups(g) {
  const T = g[MT.side];
  sortTable($('#lut'), [
    {k: 'players', t: 'Hráči', l: true, get: r => r.players.join(', '), fmt: v => `<span style="white-space:normal">${esc(v)}</span>`, s: false},
    {k: 'min', t: 'Min', get: r => r.min, fmt: f1}, {k: 'sc', t: 'Skóre', get: r => r.pf, fmt: (v, r) => r.pf + ':' + r.pa},
    {k: 'pm', t: '+/−', get: r => r.pm, fmt: signed, cls: cls}, {k: 'ortg', t: 'ORtg', get: r => r.ortg, fmt: f1}, {k: 'drtg', t: 'DRtg', get: r => r.drtg, fmt: f1, asc: true},
    {k: 'net', t: 'Net', get: r => r.net, fmt: v => `<b>${signed(v)}</b>`, cls: cls}, {k: 'efg', t: 'eFG my/soup.', get: r => r.efg, fmt: (v, r) => f0(r.efg) + ' / ' + f0(r.oefg)}],
    T.lineups[MT.lu], {sort: 'min'});
}

function shotChart(shots, col) {
  // polovina hřiště 14 × 15 m, koš vlevo (souřadnice FIBA v % délky 28 m a šířky 15 m)
  const W = 420, H = 450, sx = W / 14, sy = H / 15;
  const mx = x => x / 100 * 28 * sx, my = y => y / 100 * 15 * sy;
  const hx = mx(5.2), hy = H / 2, r3 = 6.75 * sx, keyW = 4.9 * sy, keyL = 5.8 * sx;
  const cornerY = 6.6 * sy, ang = Math.asin(cornerY / r3), cx = hx + r3 * Math.cos(ang);
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" style="max-width:420px;margin:0 auto;background:var(--court)">
    <g fill="none" stroke="#6f6e66" stroke-width="2">
      <rect x="1" y="1" width="${W - 2}" height="${H - 2}"/>
      <rect x="1" y="${(H - keyW) / 2}" width="${keyL}" height="${keyW}"/>
      <path d="M${1 + keyL},${H / 2 - 1.8 * sy} A${1.8 * sy},${1.8 * sy} 0 0 1 ${1 + keyL},${H / 2 + 1.8 * sy}"/>
      <line x1="1" y1="${hy - cornerY}" x2="${cx}" y2="${hy - cornerY}"/><line x1="1" y1="${hy + cornerY}" x2="${cx}" y2="${hy + cornerY}"/>
      <path d="M${cx},${hy - cornerY} A${r3},${r3} 0 0 1 ${cx},${hy + cornerY}"/>
      <circle cx="${hx}" cy="${hy}" r="${0.23 * sx}" stroke="${col}"/>
    </g>
    ${shots.map(s => s[2]
      ? `<circle cx="${mx(s[0]).toFixed(1)}" cy="${my(s[1]).toFixed(1)}" r="5" fill="${col}" stroke="#2d2d2d" stroke-width="1.5"/>`
      : `<g stroke="#a3a29a" stroke-width="1.8"><line x1="${mx(s[0]) - 4}" y1="${my(s[1]) - 4}" x2="${mx(s[0]) + 4}" y2="${my(s[1]) + 4}"/><line x1="${mx(s[0]) - 4}" y1="${my(s[1]) + 4}" x2="${mx(s[0]) + 4}" y2="${my(s[1]) - 4}"/></g>`).join('')}
  </svg><div class="caption" style="text-align:center">● proměněná · × minutá</div>`;
}

route();
})();
