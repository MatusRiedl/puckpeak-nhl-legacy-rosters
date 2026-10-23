// The team list on the left of the six team tabs: a league, its teams with a code chip in their colours and one small
// number for the tab in view (players, games or cap space). Drawn once, outside the panes, so it keeps its scroll; the
// list is Python's (app/editor.py rail_view), the pick goes back there and every team tab follows it.
import { html, cls, useEffect, useRef } from './lib.js';
import { call } from './bridge.js';

function light(hex) {
  const n = parseInt(String(hex || '#000000').slice(1), 16);
  const [r, g, b] = [n >> 16, (n >> 8) & 255, n & 255];
  return 0.299 * r + 0.587 * g + 0.114 * b > 165;
}

// a team's short code in its colours (no logos)
export function Code({ team, small }) {
  if (!team) return null;
  const [c1, c2] = team.colours || ['#2c4560', '#ffffff'];
  return html`<span class=${cls('code', small && 'small')} title=${team.name}
    style=${{ background: c1, color: light(c1) ? '#0b1829' : '#fff', boxShadow: `inset 0 -3px 0 ${c2}` }}>${team.code}</span>`;
}

export function Rail({ s }) {
  const list = useRef(null);
  const picked = s && s.rows ? (s.rows.find((r) => r.sel) || {}).id : null;
  useEffect(() => {
    const el = list.current && list.current.querySelector('.rteam.sel');
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [picked, s && s.league]);
  if (!s) return html`<aside class="card rail"></aside>`;
  const pick = (id) => call('rail_team', id);
  return html`<aside class="card rail">
    <header class="card-head"><span class="title">Teams</span><span class="aside">${s.tip}</span></header>
    <div class="rail-league">
      <select class="field select" value=${s.league || ''} disabled=${!s.loaded} aria-label="League"
        onChange=${(e) => call('rail_league', e.target.value)}>
        ${s.leagues.map((l) => html`<option key=${l.value} value=${l.value}>${l.label}</option>`)}
      </select>
    </div>
    <div class="scroll" ref=${list}><div class="rlist" role="listbox" aria-label="Teams">
      ${s.rows.map((r) => html`<div key=${r.id} role="option" aria-selected=${r.sel} tabindex="0"
          class=${cls('rteam', r.sel && 'sel')} onClick=${() => pick(r.id)}
          onKeyDown=${(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(r.id); } }}>
        <${Code} team=${r}/>
        <span class="rname" title=${r.name}>${r.name}${r.farm && html`<span class="rfarm">${r.farm}</span>`}</span>
        ${r.dirty && html`<span class="rdot" title="Changed, not applied yet"></span>`}
        ${r.number && html`<span class=${cls('rnum', r.number.tone)} title=${r.number.tip}>${r.number.text}</span>`}
      </div>`)}
      ${!s.loaded && html`<div class="empty small">${s.status}</div>`}
    </div></div>
  </aside>`;
}
