// The Draft & Pro tab: made-up prospects for the next four drafts of a new Be a GM / Season (the draft classes) and the
// player's own Be a Pro player. The classes stand where the other team tabs have the team list; a class's players are
// listed beside the Roster editor's card (the same card: Apply, Undo and the Save bar work as on the Roster tab), which
// gets a prospect part: the growth tier and the potential the game drafts him by. Python: app/prospects.py. Last in the
// list, "Be a Pro careers": the player's running careers, the pro's name, ratings and XP changed and saved back
// (app/career.py).
import { html, cls, useEffect, useRef, useState } from './lib.js';
import { call } from './bridge.js';
import { Button, Card, Modal, Segmented, TextField } from './ui.js';
import { Code } from './rail.js';
import { PlayerCard, useCardForm, cardDraft } from './editor.js';

const CLASS_COLOURS = ['#163a5f', '#d4a537'];
const PRO_COLOURS = ['#6d1f2b', '#f2f2f2'];
const CAREER_COLOURS = ['#1d4d2f', '#f2f2f2'];
// the columns' widths are in teams.css (.pr-grid), with a narrower set for the smallest window
const COLUMNS = [['pos', 'Pos'], ['name', 'Name'], ['born', 'Born'], ['club', 'Club'], ['tier', 'Stars'], ['potential', 'Pot'],
  ['ovr', 'OVR']];
const PRO_COLUMNS = COLUMNS.filter(([key]) => key !== 'tier' && key !== 'potential');
const count = (n) => (n === 1 ? '1 player' : `${n} players`);

const chip = (v) => {
  if (v.value === 'pro') return { code: 'PRO', name: v.label, colours: PRO_COLOURS };
  if (v.value === 'careers') return { code: 'BAP', name: v.label, colours: CAREER_COLOURS };
  return { code: `'${String(v.value).slice(2)}`, name: v.label, colours: CLASS_COLOURS };
};
const RAIL_TIPS = { pro: 'Your pro', careers: 'Be a Pro careers saved in the game' };

// the classes (and My pro) on the left, with how many players each has
export function ClassRail({ p }) {
  const list = useRef(null);
  useEffect(() => {
    const el = list.current && list.current.querySelector('.rteam.sel');
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [p && p.view]);
  if (!p) return html`<aside class="card rail"></aside>`;
  const pick = (v) => call('prospects_show', v);
  return html`<aside class="card rail pr-rail">
    <header class="card-head"><span class="title">Drafts</span><span class="aside">players</span></header>
    <div class="scroll" ref=${list}><div class="rlist" role="listbox" aria-label="Draft classes">
      ${p.views.map((v) => html`<div key=${v.value} role="option" aria-selected=${v.value === p.view} tabindex="0"
          class=${cls('rteam', v.value === p.view && 'sel', v.value === 'pro' && 'pr-pro')} onClick=${() => pick(v.value)}
          onKeyDown=${(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(v.value); } }}>
        <${Code} team=${chip(v)}/>
        <span class="rname" title=${v.label}>${v.label}</span>
        <span class="rnum" title=${RAIL_TIPS[v.value] || 'Players in this class'}>${v.count}</span>
      </div>`)}
      ${!p.loaded && html`<div class="empty small">${p.why}</div>`}
    </div></div>
    ${p.room && html`<div class="pr-room" title=${p.room.text}>
      <b>${p.room.skaters}</b> skaters and <b>${p.room.goalies}</b> goalies more fit in this roster.</div>`}
  </aside>`;
}

// the players of the class in view
function Rows({ p }) {
  const body = useRef(null);
  useEffect(() => {
    const el = body.current && body.current.querySelector('.prow.sel');
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [p.selected, p.view]);
  const pick = (key) => call('prospects_pick', key, cardDraft.current);
  const pro = p.view === 'pro';
  const cols = pro ? PRO_COLUMNS : COLUMNS;
  return html`<div class=${cls('ptable', 'pr-grid', pro && 'pro')}>
    <div class="phead">${cols.map(([key, title]) => html`<span key=${key} class="th">${title}</span>`)}</div>
    <div class="pbody scroll" ref=${body} tabindex="0">
      ${p.rows.length === 0 && html`<div class="empty small">${p.view === 'pro'
        ? 'No pro yet. Make one: he is yours to pick in Be a Pro.'
        : 'Nobody in this class yet. Add a prospect: the game drafts him in this draft.'}</div>`}
      ${p.rows.map((r) => html`<div key=${r.key} class=${cls('prow', `pr-${r.state}`, r.key === p.selected && 'sel')}
          title=${r.note} onClick=${() => pick(r.key)}>
          <span>${r.pos}</span><span class="name">${r.name}</span><span class="num">${r.born}</span>
          <span class="note">${r.club}</span>
          ${!pro && html`<span class="num" title=${`Growth tier ${r.tier}`}>${r.stars}★</span><span class="num">${r.potential}</span>`}
          <span class="num ovr">${r.ovr}</span>
        </div>`)}
    </div>
  </div>`;
}

// the prospect part of the card: the growth tier (the game's Potential Range in stars) and the potential it drafts him by
function ProspectPart({ p }) {
  const b = p.prospect;
  if (!b) return null;
  const range = b.lo === b.hi;
  return html`<div class="pr-part">
    <div class="pc-sub">Draft prospect</div>
    <div class="pr-row"><span>Potential range <span class="faint">(stars)</span></span>
      <${Segmented} className="tiny pr-tiers" value=${b.tier}
        options=${p.tiers.map((t) => ({ value: t.value, label: t.label }))}
        onChange=${(v) => call('prospects_set', 'tier', v)}/></div>
    <div class="pr-row"><span>Potential</span>
      <span class="pr-pot">
        <input type="range" class="ct-slider" min=${b.lo} max=${b.hi} value=${b.potential} disabled=${range}
          aria-label="Potential" onChange=${(e) => call('prospects_set', 'potential', Number(e.target.value))}/>
        <b>${b.potential}</b></span></div>
    <div class="pc-note">${`${b.stars} stars (growth tier ${b.tier}): ${b.hint}. The game keeps his potential at ${range ? b.lo : `${b.lo}-${b.hi}`} for this range.`}</div>
  </div>`;
}

// the random maker: how many players, how strong a class, and its number (the same number makes the same class)
function MakerWindow({ m }) {
  const set = (field, value) => call('prospects_make_set', field, value);
  const close = () => call('prospects_close');
  return html`<${Modal} title=${`Make a random ${m.year} draft class`} onClose=${close} buttons=${html`
      <${Button} kind="gold" onClick=${() => call('prospects_make')}>Make ${m.count} players<//>
      <${Button} onClick=${close}>Cancel<//>`}>
    <div class="pr-make">
      <div class="pr-row"><span>Players</span>
        <${Segmented} className="tiny" value=${m.count} options=${m.counts.map((n) => ({ value: n, label: String(n) }))}
          onChange=${(v) => set('count', v)}/></div>
      <div class="pr-row"><span>Strength</span>
        <${Segmented} className="tiny" value=${m.strength} options=${m.strengths} onChange=${(v) => set('strength', v)}/></div>
      <div class="pr-row"><span>Class number</span>
        <input type="number" class="field pr-seed" min="0" max="99999" value=${m.seed} aria-label="Class number"
          onChange=${(e) => set('seed', e.target.value)}/>
        <span class="faint">The same number makes the same class.</span></div>
      <div class="pr-split" title="How many players get each potential range (the game's stars)">
        ${m.split.map((t) => html`<div key=${t.tier} class="pr-split-t"><b>${t.count}</b><span>${t.stars}★</span></div>`)}
      </div>
      <div class="small-note">Made-up players: first and last names of different real players of the same country, never a
        real player's full name. They play on junior and European clubs, spread evenly, and are born for the ${m.year} draft.
        Change any of them on the card afterwards.</div>
    </div>
  <//>`;
}

// what an import did
function ReportWindow({ r }) {
  const close = () => call('prospects_close');
  return html`<${Modal} title=${r.title} onClose=${close} buttons=${html`<${Button} kind="pick" onClick=${close}>OK<//>`}>
    <div class="pr-report">${r.lines.map((l, k) => html`<div key=${k} class=${cls('note', l.tone)}>${l.text}</div>`)}</div>
  <//>`;
}

// a number typed and sent when the field is left or Enter is pressed (a rating of 4 on the way to 45 is not sent);
// then it shows what Python holds again
function NumberField({ value, disabled, label, onCommit }) {
  const [text, setText] = useState(String(value));
  useEffect(() => { setText(String(value)); }, [value]);
  const commit = () => { if (text !== String(value)) onCommit(text || String(value)); setText(String(value)); };
  return html`<input class="field" inputmode="numeric" value=${text} disabled=${disabled} aria-label=${label}
    onInput=${(e) => setText(e.target.value.replace(/[^0-9]/g, '').slice(0, 2))} onBlur=${commit}
    onKeyDown=${(e) => { if (e.key === 'Enter') commit(); }}/>`;
}

// a running Be a Pro career's pro: name, XP to spend and ratings changed (the game works the Overall out again)
function CareerPro({ c }) {
  const pro = c.pro;
  const busy = !!c.busy;
  if (!pro) {
    return html`<${Card} title="Your pro" className="cr-pro">
      <div class="empty small">${busy ? c.busy : (c.rows.length ? 'Pick a career.' : '')}</div><//>`;
  }
  const changed = (key) => pro.changed.includes(key);
  return html`<${Card} title=${pro.name} aside=${pro.goalie ? 'Goalie' : pro.type} className="cr-pro">
    <div class="card-body scroll">
      <div class="cr-facts">
        <span>#<b>${pro.jersey}</b></span>${pro.birthplace && html`<span>${pro.birthplace}</span>`}
      </div>
      <div class="pc-sub">Name</div>
      <div class="cr-names">
        ${['first', 'last'].map((key) => html`<label key=${key} class=${cls('cr-field', changed(key) && 'on')}>
          <span>${key === 'first' ? 'First name' : 'Last name'}</span>
          <${TextField} value=${pro[key]} disabled=${busy} delay=${600} onChange=${(v) => call('career_set', key, v)}/>
        </label>`)}
      </div>
      <div class="pc-sub">Experience to spend <span class="faint">(Player Growth)</span></div>
      <div class="cr-pools">
        ${pro.pools.map((x) => html`<label key=${x.key} class=${cls('cr-field', changed(x.key) && 'on')}>
          <span>${x.label}</span>
          <input class="field" inputmode="numeric" value=${x.value} disabled=${busy} aria-label=${`${x.label} XP`}
            onChange=${(e) => call('career_set', x.key, e.target.value.replace(/[^0-9]/g, '') || '0')}/>
          <span class="faint">${x.value !== x.was ? `was ${x.was}` : ''}</span>
        </label>`)}
      </div>
      <div class="pc-note">${`Spend it in the game: Live the Life > Player Growth. At most ${c.max_xp} in each.`}</div>
      <div class="pc-sub">Ratings <span class="faint">${`(${c.lowest}-${c.highest})`}</span></div>
      ${pro.goalie ? html`<div class="pc-note">A goalie's ratings cannot be changed here yet.</div>` : html`
      <div class="cr-ratings">
        ${pro.ratings.map((r) => html`<label key=${r.key} class=${cls('rt', changed(r.key) && 'on')}
            title=${r.value !== r.was ? `was ${r.was}` : r.label}>
          <span>${r.label}</span>
          <${NumberField} value=${r.value} disabled=${busy} label=${r.label} onCommit=${(v) => call('career_set', r.key, v)}/>
        </label>`)}
      </div>
      <div class="pc-note">The game works out the Overall from these when the career loads.</div>`}
    </div>
    <div class="card-foot row">
      <${Button} kind="gold" onClick=${() => call('career_save')} disabled=${busy || !c.dirty}>Save this career<//>
      <${Button} onClick=${() => call('career_undo')} disabled=${busy || !c.dirty}>Undo<//>
    </div>
  <//>`;
}

// the careers saved in the game (Load Pro's list), then the picked one's pro
function CareerTab({ p, c }) {
  if (!c) return null;
  return html`<div class=${cls('tt-roster', 'tt-prospects', 'tt-careers', c.busy && 'busy')}>
    <div class="tt-bar">
      <div class="pr-title">${p.title}<span class="pr-span">${p.span}</span></div>
      <${Button} small onClick=${() => call('career_look')} disabled=${!!c.busy}
        title="Look in RPCS3's save folder again">Look again<//>
    </div>
    <div class="cr-two">
      <${Card} title="Careers" aside=${c.rows.length ? String(c.rows.length) : ''} className="cr-list">
        <div class="pr-note">${p.note}</div>
        ${c.note && html`<div class=${cls('pr-note', c.note.tone)}>${c.note.text}</div>`}
        <div class="scroll cr-rows">
          ${c.rows.length === 0 && html`<div class="empty small">${c.why || 'Looking...'}</div>`}
          ${c.rows.map((r) => html`<button key=${r.folder} type="button" class=${cls('cr-row', r.folder === c.picked && 'sel')}
              disabled=${!!c.busy} onClick=${() => call('career_open', r.folder)}>
            <span class="name">${r.name}</span><span class="faint">${r.saved}</span>
          </button>`)}
        </div>
      <//>
      <${CareerPro} c=${c}/>
    </div>
  </div>`;
}

export function ProspectsTab({ s, p, c }) {
  const { form, dirty, set, setRating } = useCardForm(s);
  if (!s || !s.roster || !p) return null;
  if (p.view === 'careers') return html`<${CareerTab} p=${p} c=${c}/>`;
  const pro = p.view === 'pro';
  const mine = p.rows.some((r) => r.key === p.selected) || (s.card && s.card.new && p.prospect);
  const extra = pro && s.card && mine ? html`<div class="pr-part"><span class="pill gold">My pro</span></div>`
    : html`<${ProspectPart} p=${p}/>`;
  return html`<div class=${cls('tt-roster', 'tt-prospects', s.busy && 'busy')}>
    <div class="tt-bar">
      <div class="pr-title">${p.title}<span class="pr-span">${p.span}</span></div>
      <${Button} small kind="gold" onClick=${() => call('prospects_add')} disabled=${!p.loaded || !p.can_add}
        title=${pro ? 'A new player of your own, to pick in Be a Pro' : 'A new player for this draft'}>
        ${pro ? 'Make my pro' : 'Add a prospect'}<//>
      ${!pro && html`<${Button} small onClick=${() => call('prospects_make_open')} disabled=${!p.loaded || s.busy}
        title="A whole class of made-up players at once">Make a class...<//>`}
      ${p.selected && html`<${Button} small onClick=${() => call('prospects_remove', p.selected)} disabled=${s.busy}
        title="Take him out of the class (a player saved into the roster becomes a free agent)">Take out<//>`}
      ${!pro && html`<span class="pr-files">
        <${Button} small onClick=${() => call('prospects_import')} disabled=${!p.loaded || s.busy}
          title="Put the players of a class file into this draft">Import...<//>
        <${Button} small onClick=${() => call('prospects_export')} disabled=${!p.loaded || !p.rows.length}
          title="Save this class as a file to share">Export...<//></span>`}
    </div>
    ${p.maker && html`<${MakerWindow} m=${p.maker}/>`}
    ${p.report && html`<${ReportWindow} r=${p.report}/>`}
    <div class="tt-two">
      <${Card} title=${pro ? 'My pro' : `${p.view} draft`} aside=${p.rows.length ? count(p.rows.length) : ''}
          className="ed-players pr-list">
        <div class="pr-note">${p.note}</div>
        ${p.warn && html`<div class="pr-note warn">${p.warn}</div>`}
        ${p.unsaved && html`<div class="pr-note unsaved">${p.unsaved}</div>`}
        <${Rows} p=${p}/>
      <//>
      <${PlayerCard} s=${s} form=${form} set=${set} setRating=${setRating} dirty=${dirty} extra=${mine ? extra : null}
        empty=${pro ? 'Pick your pro, or make one.' : 'Pick a prospect, or add one.'}
        onApply=${() => call('editor_apply', form)}/>
    </div>
  </div>`;
}
