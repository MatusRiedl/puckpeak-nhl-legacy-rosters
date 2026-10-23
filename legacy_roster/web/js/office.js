// The Front office tab: an NHL organisation's money (payroll, cap, space for five seasons) and its players in three
// groups (NHL roster, farm, prospects and rights); any other team its own roster's contracts; the free agents their list.
// A click on a player opens his contract (app/office.py); a free agent signs with a team there.
import { html, cls } from './lib.js';
import { Button, Segmented, Toggle, Modal } from './ui.js';
import { call } from './bridge.js';
import { Code } from './rail.js';
import { Standings } from './calendar.js';

const COLUMNS = [['name', 'Player'], ['pos', 'Pos'], ['age', 'Age'], ['ovr', 'OVR'], ['cap', 'Cap hit'], ['years', 'Years'],
  [null, 'Type'], ['ext', 'Extension'], [null, 'Where']];

// real dollars in the player's words, as contracts.money: '$12.5M', '$850k'
export function money(x) {
  const a = Math.abs(x || 0);
  const text = a >= 999500 ? `$${(a / 1e6).toFixed(3).replace(/0+$/, '').replace(/\.$/, '')}M` : `$${Math.round(a / 1000)}k`;
  return (x < 0 ? '-' : '') + text;
}

function Head({ sort }) {
  return html`<div class="fo-row fo-th">${COLUMNS.map(([key, label]) => html`<span key=${label}
      class=${cls('c', key && 'sortable', sort.sort === key && 'on')} onClick=${key ? () => call('office_sort', key) : null}>
      ${label}${sort.sort === key ? (sort.dir > 0 ? ' ▲' : ' ▼') : ''}</span>`)}</div>`;
}

function Row({ r }) {
  const open = () => call('contract_open', r.key);
  return html`<div class=${cls('fo-row', r.edited && 'edited', r.rights && 'rights')} tabindex="0" role="button"
      onClick=${open} onKeyDown=${(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } }}>
    <span class="c name" title=${r.name}>${r.name}${r.edited && html`<span class="chip made">edited</span>`}</span>
    <span class="c">${r.pos}</span><span class="c">${r.age ?? ''}</span>
    <span class="c ovr">${r.ovr ?? ''}</span>
    <span class="c money">${r.cap_text}</span><span class="c">${r.years || ''}</span>
    <span class="c">${r.type}</span>
    <span class="c">${r.ext}</span>
    <span class="c where" title=${r.where}>${r.where}</span>
  </div>`;
}

export function ContractWindow({ c }) {
  if (!c) return null;
  const d = c.draft;
  const lim = c.limits;
  const change = (field, value) => call('contract_change', field, value);
  const step = (field, by, lo) => change(field, Math.max(lo, Math.min(lim.max, d[field] + by)));
  const nudge = lim.nudge || 250000;
  const years = (field) => html`<${Segmented} className="ct-seg" value=${d[field]} onChange=${(v) => change(field, v)}
      options=${Array.from({ length: lim.years || 8 }, (_, k) => ({ value: k + 1, label: String(k + 1) }))}/>`;
  const capRow = (field, label, lo) => html`<div class="ct-row">
    <span class="ct-label">${label}</span>
    <button type="button" class="btn ghost small" title=${`${money(nudge)} less`} onClick=${() => step(field, -nudge, lo)}>−</button>
    <input type="range" class="ct-slider" min=${lo} max=${lim.max} step=${lim.step} value=${Math.max(lo, d[field])}
      aria-label=${label} onInput=${(e) => change(field, Number(e.target.value))}/>
    <button type="button" class="btn ghost small" title=${`${money(nudge)} more`} onClick=${() => step(field, nudge, lo)}>+</button>
    <label class="ct-k" title="The amount in thousands of dollars">$<input type="number" class="field" min=${lo / 1000}
      max=${lim.max / 1000} step=${lim.step / 1000} value=${Math.round(d[field] / 1000)} aria-label=${`${label} in thousands`}
      onChange=${(e) => change(field, Number(e.target.value) * 1000)}/>k</label>
    <b class="ct-money">${money(d[field])}</b>
  </div>`;
  const join = c.join;
  return html`<${Modal} title=${c.sign || join ? `Sign ${c.name}` : `Contract: ${c.name}`} wide onClose=${() => call('contract_close')}
    buttons=${html`
      <${Button} kind="pick" disabled=${!c.can_apply} onClick=${() => call('contract_apply')}>Apply<//>
      ${c.edited && html`<${Button} onClick=${() => call('contract_reset')}
        title="The contract the roster had before your change comes back">Reset to the real deal<//>`}
      <${Button} onClick=${() => call('contract_close')}>Cancel<//>`}>
    <div class="ct">
      <div class="ct-who">${c.team && html`<${Code} team=${c.team}/>`}<span>${c.pos} · ${c.age ?? '?'} years old</span>
        <span class="faint">Now: ${c.current}</span></div>
      ${join && html`<div class="ct-row"><span class="ct-label">Signs with</span>
        <select class="field select ct-join" value=${join.value ?? ''} onChange=${(e) => change('join', e.target.value)}>
          <option value="">Pick a team...</option>
          ${join.options.map((o) => html`<option key=${o.value} value=${String(o.value)}>${o.label}</option>`)}
        </select></div>`}
      ${capRow('cap', c.nhl ? 'Cap hit' : 'Per season', lim.min)}
      <div class="ct-row"><span class="ct-label">Years</span>${years('years')}</div>
      ${c.nhl && html`<div class="ct-row"><span class="ct-label">Two-way</span><${Toggle} on=${d.two_way} label="Two-way"
          onChange=${(v) => change('two_way', v)}/>
        <span class="faint">${d.two_way ? 'Paid less while he plays on the farm.' : 'Paid the same wherever he plays.'}</span></div>`}
      <div class="ct-row"><span class="ct-label">Extension</span><${Toggle} on=${d.ext_on} label="Extension"
          onChange=${(v) => change('ext_on', v)}/>
        <span class="faint">${d.ext_on ? 'A new deal that starts when this one ends.' : 'None.'}</span></div>
      ${d.ext_on && html`<div class="ct-ext">
        <div class="ct-row"><span class="ct-label">Its years</span>${years('ext_years')}</div>
        ${capRow('ext_cap', c.nhl ? 'Its cap hit' : 'Its pay', lim.ext_min || lim.min)}
      </div>`}
      <div class="ct-years">${c.years.map((y) => html`<div key=${y.label} class=${cls('ct-y', y.on && 'on', y.ext && y.on && 'ext')}>
        <span>${y.label}</span><b>${y.on ? y.cap : '-'}</b></div>`)}</div>
      ${c.preview && html`<div class="ct-preview">${c.preview.label}: <b>${c.preview.before}</b> → <b class=${c.preview.tone}>${c.preview.after}</b>
        ${c.preview.note && html`<div class="faint">${c.preview.note}</div>`}</div>`}
      ${c.problems.map((p, k) => html`<div key=${k} class=${cls('note', p.tone)}>${p.text}</div>`)}
      <div class="small-note">Apply keeps it in My edits${join ? ' (he moves to the team too)' : ''}. Save writes it into the roster.</div>
    </div>
  <//>`;
}

function Season({ y }) {
  if (y.cap == null) {                  // a club: no cap
    return html`<div class="fo-season">
      <div class="l"><b>${y.label}</b><span class="good">${y.committed}</span></div>
      <div class="bar"><span style=${{ width: `${Math.round(y.share * 100)}%` }}></span></div>
      <div class="s">${y.signed_text}</div>
    </div>`;
  }
  return html`<div class="fo-season">
    <div class="l"><b>${y.label}</b><span class=${y.tone}>${y.space}<i class="w"> space</i></span></div>
    <div class="bar"><span class=${y.tone} style=${{ width: `${Math.round(y.share * 100)}%` }}></span></div>
    <div class="s">${y.committed} of ${y.cap} · ${y.signed} signed</div>
  </div>`;
}

export function OfficeTab({ s }) {
  if (!s) return null;
  if (s.why) return html`<div class="why card">${s.team && html`<${Code} team=${s.team}/>`}<p>${s.why}</p></div>`;
  const n = s.counts;
  const groups = n && [{ value: 'all', label: 'All' }, { value: 'nhl', label: `NHL roster (${n.nhl ?? 0})` },
    { value: 'farm', label: `Farm (${n.farm ?? 0})` }, { value: 'prospects', label: `Prospects (${n.prospects ?? 0})` }];
  return html`<div class="fo">
    <div class="fo-top">
      <div class="fo-team"><${Code} team=${s.team}/><div><b>${s.team.name}</b>
        ${s.link && html`<span class="faint">${s.link.text} · <a class="fo-link" role="button" tabindex="0"
          onClick=${() => call('rail_team', s.link.team.id)}>${s.link.button}</a></span>`}</div></div>
      ${s.tiles.map((t) => html`<div key=${t.label} class=${cls('tile', t.minor && 'minor', t.season && 'wide')}>
        <b class=${t.tone || ''}>${t.value}</b><span title=${t.label}>${t.label}</span></div>`)}
    </div>
    ${s.about && html`<div class="fo-about">${s.about}</div>`}
    ${s.seasons.length > 0 && html`<div class="fo-seasons">${s.seasons.map((y) => html`<${Season} key=${y.label} y=${y}/>`)}</div>`}
    <div class=${cls('fo-main', s.standings && 'with-stand')}>
    <section class="card grow fo-table">
      <header class="card-head"><span class="title">Contracts</span>
        ${groups && html`<${Segmented} value=${s.group} options=${groups} onChange=${(g) => call('office_group', g)}/>`}
        <span class="aside">${s.edited ? `${s.edited} set by hand · ` : ''}${s.kind === 'free' ? 'click a player to sign him' :
          'click a player to change his contract'}</span></header>
      <${Head} sort=${s.sort}/>
      <div class="scroll">
        ${s.groups.map((g) => html`<div key=${g.key} class="fo-group">
          <div class="fo-gtitle">${g.title}<span>${g.rows.length}</span></div>
          ${g.note && html`<div class="fo-note">${g.note}</div>`}
          ${g.rows.map((r) => html`<${Row} key=${r.key} r=${r}/>`)}
        </div>`)}
      </div>
      <footer class="fo-foot">${s.note}</footer>
    </section>
    ${s.standings && html`<${Standings} st=${s.standings}/>`}
    </div>
  </div>`;
}
