// The Roster editor tab: teams | players (sortable) | the player's card, the save bar, and the Team,
// My edits and Jerseys and ice windows. Python holds the roster; what is typed on the card stays here
// until Apply, Save or a pick of another player sends it along (app/editor.py).
import { html, cls, useState, useEffect, useRef, useMemo } from './lib.js';
import { call } from './bridge.js';
import { useSlice } from './store.js';
import { Button, Segmented, Card, RegionTag, TextField, Modal } from './ui.js';

const COLUMNS = [
  { key: 'pos', title: 'Pos', w: '44px' }, { key: 'num', title: '#', w: '38px' }, { key: 'name', title: 'Name', w: 'minmax(120px, 1.4fr)' },
  { key: 'age', title: 'Age', w: '44px' }, { key: 'nat', title: 'Nat', w: '48px' }, { key: 'ovr', title: 'OVR', w: '48px' },
  { key: 'note', title: 'Change', w: 'minmax(90px, 1fr)' },
];
const GRID = COLUMNS.map((c) => c.w).join(' ');
const FIELDS = [
  ['first', 'First name'], ['last', 'Last name'], ['num', 'Number'], ['pos', 'Position'], ['shoots', 'Shoots'],
  ['birth', 'Born (YYYY-MM-DD)'], ['country', 'Country'], ['height', 'Height (cm)'], ['weight', 'Weight (kg)'],
  ['team', 'Team'], ['ovr', 'Overall'],
];
const SAVE_MODES = [{ value: 'update', label: 'Update this roster' }, { value: 'new', label: 'Save as a new roster' }];

function sortValue(row, key) {
  const v = row[key];
  const n = typeof v === 'number' ? v : parseFloat(v);
  return Number.isFinite(n) && String(v).trim() !== '' ? [0, n] : [1, String(v).toLowerCase()];
}

function sorted(rows, sort) {
  if (!sort) return rows;
  const out = rows.slice();
  out.sort((a, b) => {
    const x = sortValue(a, sort.key), y = sortValue(b, sort.key);
    const c = x[0] - y[0] || (x[1] < y[1] ? -1 : x[1] > y[1] ? 1 : 0);
    return sort.desc ? -c : c;
  });
  return out;
}

// --- the left pane: league and teams ------------------------------------------------------------
function Teams({ s }) {
  const list = useRef(null);
  useEffect(() => {
    const el = list.current && list.current.querySelector('.team.sel');
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [s.team, s.league]);
  return html`<${Card} title="Teams" className="ed-teams">
    <div class="card-body fill">
      <select class="field select" value=${s.league || ''} disabled=${!s.loaded}
        onChange=${(e) => call('editor_league', e.target.value)}>
        ${s.leagues.map((l) => html`<option key=${l} value=${l}>${l}</option>`)}
      </select>
      <div class="scroll team-list" ref=${list}>
        ${s.teams.map((t) => html`<div key=${t.id} class=${cls('team', !s.searching && t.id === s.team && 'sel')}
            onClick=${() => call('editor_team', t.id)}>
            <span class="n">${t.name}</span><span class="c">${t.count}</span></div>`)}
      </div>
    </div>
  <//>`;
}

// --- the middle: the players ----------------------------------------------------------------------
function Players({ s, onPick }) {
  const [sort, setSort] = useState(null);
  const rows = useMemo(() => sorted(s.rows, sort), [s.rows, sort]);
  const body = useRef(null);
  const pickBy = (step) => {
    if (!rows.length) return;
    const at = rows.findIndex((r) => r.who === s.selected && r.tag !== 'left');
    const next = rows[Math.max(0, Math.min(rows.length - 1, at < 0 ? 0 : at + step))];
    if (next) onPick(next.id);
  };
  useEffect(() => {
    const el = body.current && body.current.querySelector('.prow.sel');
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [s.selected, rows]);
  const head = (c) => {
    const on = sort && sort.key === c.key;
    return html`<button type="button" key=${c.key} class=${cls('th', on && 'on')}
      onClick=${() => setSort(on ? { key: c.key, desc: !sort.desc } : { key: c.key, desc: c.key === 'ovr' || c.key === 'age' })}>
      ${c.title}${on && html`<span class="arrow">${sort.desc ? '▼' : '▲'}</span>`}</button>`;
  };
  const title = s.searching ? `${s.rows.length} found for “${s.query}”` : s.team_name;
  return html`<${Card} title=${title || 'Players'} aside=${s.rows.length ? `${s.rows.length} players` : ''} className="ed-players">
    <div class="ptable" style=${{ '--grid': GRID }}>
      <div class="phead">${COLUMNS.map(head)}</div>
      <div class="pbody scroll" ref=${body} tabindex="0"
        onKeyDown=${(e) => {
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); pickBy(e.key === 'ArrowDown' ? 1 : -1); }
        }}>
        ${rows.length === 0 && html`<div class="empty small">${s.searching ? 'Nobody by that name.' : 'No players.'}</div>`}
        ${rows.map((r) => html`<div key=${r.id} class=${cls('prow', r.tag, r.who === s.selected && r.tag !== 'left' && 'sel')}
            onClick=${() => onPick(r.id)}>
            <span>${r.pos}</span><span class="num">${r.num}</span><span class="name">${r.name}</span>
            <span class="num">${r.age}</span><span>${r.nat}</span><span class="num ovr">${r.ovr}</span>
            <span class="note" title=${r.note}>${r.note}</span></div>`)}
      </div>
    </div>
  <//>`;
}

// --- the right: the player's card -------------------------------------------------------------------
function Picture() {
  const p = useSlice('picture');
  if (!p || (!p.url && !p.caption)) return html`<div class="portrait none"></div>`;
  return html`<div class=${cls('portrait', p.loading && 'loading')}>
    ${p.url ? html`<img key=${p.url.length + ':' + p.token} src=${p.url} alt=""/>` : html`<div class="silhouette"></div>`}
    <div class="caption">${p.caption}</div>
  </div>`;
}

function Field({ k, form, set, card, choices, disabled }) {
  const v = form[k] == null ? '' : form[k];
  if (k === 'pos') {
    return html`<select class="field select" value=${v} disabled=${disabled} onChange=${(e) => set(k, e.target.value)}>
      ${choices.positions.map((p) => html`<option key=${p} value=${p}>${p}</option>`)}</select>`;
  }
  if (k === 'shoots') {
    return html`<${Segmented} className="tiny" value=${v} disabled=${disabled}
      options=${[{ value: 'L', label: 'L' }, { value: 'R', label: 'R' }]} onChange=${(x) => set(k, x)}/>`;
  }
  if (k === 'country') {
    const list = choices.countries.includes(v) || !v ? choices.countries : [v, ...choices.countries];
    return html`<select class="field select" value=${v} disabled=${disabled} onChange=${(e) => set(k, e.target.value)}>
      ${list.map((c) => html`<option key=${c} value=${c}>${c}</option>`)}</select>`;
  }
  if (k === 'team') {
    return html`<select class="field select" value=${String(v)} disabled=${disabled}
      onChange=${(e) => set(k, e.target.value === 'FA' ? 'FA' : Number(e.target.value))}>
      ${choices.teams.map(([value, label]) => html`<option key=${value} value=${String(value)}>${label}</option>`)}</select>`;
  }
  const off = disabled || (k === 'ovr' && !card.new);
  return html`<input class="field" value=${v} disabled=${off} spellcheck="false"
    inputmode=${['num', 'height', 'weight', 'ovr'].includes(k) ? 'numeric' : undefined}
    placeholder=${k === 'birth' ? '2004-11-16' : ''} onInput=${(e) => set(k, e.target.value)}/>`;
}

function PlayerCard({ s, form, set, setRating, dirty, onApply }) {
  const card = s.card;
  if (!card) {
    return html`<${Card} title="Player" className="ed-card">
      <div class="card-body fill"><div class="empty">${s.loaded ? 'Pick a player, or make a new one.' : ''}</div></div><//>`;
  }
  const labels = card.new && form.pos === 'G' ? card.goalie_labels : card.labels;
  const busy = s.busy;
  return html`<${Card} title=${card.new ? 'New player' : 'Player'} aside=${dirty ? html`<span class="pill">not applied</span>` : ''}
      className="ed-card">
    <div class="card-body scroll" key=${card.key}
      onKeyDown=${(e) => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') { e.preventDefault(); onApply(); } }}>
      <div class="pc-title">${card.title}</div>
      <div class="pc-note">${card.note}</div>
      <${Picture}/>
      <div class="row">
        <${Button} small onClick=${() => call('editor_photo')} disabled=${busy}>Choose picture...<//>
        ${!card.new && card.equipment && html`<${Button} small onClick=${() => call('equipment_open')} disabled=${busy}
          title="Stick, tape, helmet, visor, gloves, skates, the tucks; for a goalie also the mask (with a picture of your own), pads, blocker and trapper">Equipment...<//>`}
      </div>
      <div class="pc-form">
        ${FIELDS.map(([k, label]) => html`<label key=${k} class="pc-row"><span>${label}</span>
          <${Field} k=${k} form=${form} set=${set} card=${card} choices=${s.choices} disabled=${busy}/></label>`)}
      </div>
      <div class="pc-sub">Ratings <span class="faint">(40-99)</span></div>
      <div class="pc-ratings">
        ${labels.map((a) => html`<label key=${a} class="rt"><span title=${a}>${a}</span>
          <input class="field" inputmode="numeric" maxlength="2" value=${(form.ratings || {})[a] || ''} disabled=${busy}
            onInput=${(e) => setRating(a, e.target.value.replace(/[^0-9]/g, ''))}/></label>`)}
      </div>
    </div>
    <div class="card-foot row">
      <${Button} kind="primary" onClick=${onApply} disabled=${busy}>Apply<//>
      <${Button} onClick=${() => call('editor_undo')} disabled=${busy || !card.undo}>Undo my edit<//>
    </div>
  <//>`;
}

// --- the windows ---------------------------------------------------------------------------------------
function TeamWindow({ m }) {
  const [fields, setFields] = useState(m.fields);
  return html`<${Modal} title=${m.name} onClose=${() => call('modal_close')} buttons=${html`
      <${Button} kind="pick" onClick=${() => call('team_apply', fields)}>Apply<//>
      <${Button} onClick=${() => call('team_undo')} disabled=${!m.mine}>Undo team edit<//>
      <${Button} onClick=${() => call('modal_close')}>Close<//>`}>
    <p class="small-note">The game's menus show these names and the logo after an update with "Photos and logos" on.</p>
    <div class="tw-form">
      ${[['full', 'Full name'], ['city', 'City'], ['abbr', 'Abbreviation']].map(([k, label]) => html`
        <label key=${k} class="pc-row"><span>${label}</span>
          <input class="field" value=${fields[k] || ''} spellcheck="false"
            onInput=${(e) => setFields({ ...fields, [k]: e.target.value })}/></label>`)}
    </div>
    <div class="tw-logo">
      <div class="logo-box">${m.logo ? html`<img src=${m.logo} alt=""/>` : html`<span class="faint">${m.logo_text || 'the game’s logo'}</span>`}</div>
      <${Button} small onClick=${() => call('team_logo')}>Choose logo...<//>
    </div>
  <//>`;
}

function EditsWindow({ m }) {
  return html`<${Modal} title="My edits" onClose=${() => call('modal_close')}
      buttons=${html`<${Button} kind="pick" onClick=${() => call('modal_close')}>Close<//>`}>
    <p class="small-note">Kept on this PC and applied after every update (the Update tab's My edits switch). Removing one
      stops that; a roster that was saved with it keeps it.</p>
    <div class="list edits-list">
      ${m.items.length === 0 && html`<div class="empty small">No edits yet.</div>`}
      ${m.items.map((it) => html`<div key=${it.kind + it.key} class="edit-row">
          <span class=${cls('chip', it.kind === 'team' ? 'made' : 'muted')}>${it.kind === 'team' ? 'Team' : 'Player'}</span>
          <span class="n">${it.name}</span><span class="w">${it.what}</span>
          <${Button} small kind="danger" onClick=${() => call('edits_remove', it.kind, it.key)}>Remove<//></div>`)}
    </div>
  <//>`;
}

function Thumb({ url, loading, size = 78 }) {
  return html`<div class=${cls('thumb-box', !url && 'none')} style=${{ width: size + 'px', height: size + 'px' }}>
    ${url ? html`<img src=${url} alt=""/>` : html`<span>${loading ? '' : 'no picture'}</span>`}</div>`;
}

function Colour({ part, label, c }) {
  return html`<label class="pc-row colour"><span>${label}</span>
    <${TextField} value=${c.text} onChange=${(t) => call('uniforms_colour', part, t)}/>
    <span class="swatch" style=${{ background: c.hex }}>
      <input type="color" value=${c.hex} onChange=${(e) => call('uniforms_colour', part, e.target.value)}/></span>
  </label>`;
}

function UniformsWindow({ u }) {
  const thumbs = useSlice('thumbs') || {};
  return html`<${Modal} wide title=${u.title} onClose=${() => call('uniforms_close')} buttons=${html`
      <${Button} kind="pick" onClick=${() => call('uniforms_apply')}>Apply<//>
      <${Button} onClick=${() => call('uniforms_undo')}>Undo all for this team<//>
      <${Button} onClick=${() => call('uniforms_close')}>Close<//>`}>
    <p class="small-note">Pick how each jersey version is made. The game shows the change after an update with "Photos, logos
      and team names" on; "Restore the game's own pictures" puts the game's own back. A jersey made from colours uses the
      team's logo as its crest.</p>
    ${u.note && html`<div class="note warn">${u.note}</div>`}
    <div class="uw-colours">
      <${Colour} part="primary" label="Main colour" c=${u.colours.primary}/>
      <${Colour} part="secondary" label="Second colour" c=${u.colours.secondary}/>
      <div class="row crest"><span class="small-note">${u.crest}</span>
        <${Button} small onClick=${() => call('uniforms_crest', true)}>Crest picture...<//>
        <${Button} small onClick=${() => call('uniforms_crest', false)} disabled=${!u.crest_mine}>Team logo<//></div>
    </div>
    ${!u.loaded && html`<div class="empty small">Reading the game's jerseys...</div>`}
    <div class="list uw-rows">
      ${u.rows.map((r) => html`<div key=${r.variant} class="uw-row">
          <${Thumb} url=${thumbs[String(r.variant)]} loading=${u.pictures}/>
          <div class="main"><div class="t">${r.label}</div>
            <${Segmented} value=${r.mode} options=${r.options.map(([value, label]) => ({ value, label }))}
              onChange=${(x) => call('uniforms_pick', r.variant, x)}/></div>
          <${Button} small onClick=${() => call('uniforms_template', r.variant)} disabled=${!u.pictures}>Save a template...<//>
        </div>`)}
      ${u.loaded && html`<div class="uw-sub">Centre-ice logo</div>
        <div class="uw-row">
          <${Thumb} url=${thumbs.ice} loading=${u.pictures}/>
          <div class="main">
            <${Segmented} value=${u.ice.mode} options=${u.ice.options.map(([value, label]) => ({ value, label }))}
              onChange=${(x) => call('uniforms_ice', x)}/>
            <label class="pc-row arena"><span>Arena name on the ice</span>
              <${TextField} value=${u.ice.arena} onChange=${(t) => call('uniforms_arena', t)} delay=${400}/></label>
            <div class="small-note faint">A picture of your own: 1024 x 1024 with a clear background; the strip in the middle,
              where the red line crosses, is made clear by the program.</div>
          </div>
          <${Button} small onClick=${() => call('uniforms_template', 'ice')} disabled=${!u.pictures}>Save a template...<//>
        </div>`}
    </div>
  <//>`;
}

// the model pictures of one choice: the one in use is brought into view when the window opens
function EqGrid({ r, pics, loaded }) {
  const box = useRef(null);
  useEffect(() => {
    const el = box.current && box.current.querySelector('.eq-opt.on');
    if (el) box.current.scrollTop = Math.max(0, el.offsetTop - 4);
  }, [r.choice, loaded]);
  return html`<div class="eq-grid scroll" ref=${box}>${r.items.map((it) => html`<button type="button" key=${it.value}
      class=${cls('eq-opt', it.value === r.value && 'on')} title=${r.label + ' ' + it.value}
      onClick=${() => call('equipment_pick', r.choice, it.value)}>
      ${(pics[r.choice] || {})[String(it.value)] ? html`<img src=${pics[r.choice][String(it.value)]} alt=""/>` : ''}
      <span>${it.value}</span></button>`)}</div>`;
}

function EquipmentWindow({ q }) {
  const pics = useSlice('equip_pics') || {};
  return html`<${Modal} wide title=${q.title} onClose=${() => call('equipment_close')} buttons=${html`
      <${Button} kind="pick" onClick=${() => call('equipment_apply', false)} disabled=${!q.can_player}>Apply to this player<//>
      <${Button} onClick=${() => call('equipment_apply', true)} disabled=${!q.can_team}
        title="Tape, helmet, visor and the tucks, for every skater of the team without a choice of his own">
        Apply to the whole team${q.team ? ' (' + q.team + ')' : ''}<//>
      <${Button} onClick=${() => call('equipment_undo')} disabled=${!q.undo}>Take back my equipment edits<//>
      <${Button} onClick=${() => call('equipment_close')}>Close<//>`}>
    <p class="small-note">Pick what the player uses. The game shows it in a new roster, or after "Save to this roster". The
      pictures are the game's own; a stick or helmet of 2026 is the nearest model the game has. Tape, helmet, visor and the tucks
      can also be set for a whole team.</p>
    ${q.note && html`<div class="note warn">${q.note}</div>`}
    ${q.goalie && html`<div class="eq-row mask-pic">
      <div class="t">Own picture on the mask${q.mask_picture ? html` <span class="pill">changed</span>` : ''}</div>
      <div class="row">
        <${Button} small onClick=${() => call('equipment_mask_picture')}>My picture...<//>
        <${Button} small onClick=${() => call('equipment_mask_template')}>Save the mask layout to paint on<//>
        <${Button} small onClick=${() => call('equipment_mask_clear')} disabled=${!q.mask_picture}>Game's own mask<//>
      </div>
      <p class="small-note">${q.mask_picture ? 'Picture: ' + q.mask_picture : 'No picture of your own: the goalie wears the mask picked below.'}${' '}
        Keep it 512 x 512. The goalie gets a mask number nobody wears, so no other goalie changes. Shown in the game after
        "Photos, logos and team names" is run.</p>
    </div>`}
    <div class="list eq-rows">
      ${q.rows.map((r) => html`<div key=${r.choice} class=${cls('eq-row', r.touched && 'touched')}>
          <div class="t">${r.label}${r.touched ? html` <span class="pill">changed</span>` : ''}</div>
          ${r.kind === 'buttons'
            ? html`<div class="eq-buttons">${r.items.map((it) => html`<button type="button" key=${it.value}
                class=${cls('eq-opt', it.value === r.value && 'on')}
                onClick=${() => call('equipment_pick', r.choice, it.value)}>
                ${r.picture && pics[r.choice] && pics[r.choice][String(it.value)]
                  ? html`<img src=${pics[r.choice][String(it.value)]} alt=""/>` : ''}<span>${it.label}</span></button>`)}</div>`
            : html`<${EqGrid} r=${r} pics=${pics} loaded=${q.loaded}/>`}
        </div>`)}
      ${!q.loaded && html`<div class="empty small">Reading the game's pictures...</div>`}
    </div>
  <//>`;
}

// --- the tab ----------------------------------------------------------------------------------------------
export function EditorTab({ s, shown, onGoUpdate }) {
  const uniforms = useSlice('uniforms');
  const equipment = useSlice('equipment');
  const [form, setForm] = useState({});
  const [dirty, setDirty] = useState(false);
  const cardKey = s && s.card ? s.card.key : null;
  useEffect(() => {                   // a card filled again by Python: what was typed is taken or dropped there
    setForm(s && s.card ? { ...s.card.values, ratings: { ...s.card.values.ratings } } : {});
    setDirty(false);
  }, [cardKey]);
  const set = (k, v) => { setForm((f) => ({ ...f, [k]: v })); setDirty(true); };
  const setRating = (a, v) => { setForm((f) => ({ ...f, ratings: { ...(f.ratings || {}), [a]: v } })); setDirty(true); };
  const typed = () => (dirty ? form : null);
  const apply = () => call('editor_apply', form);
  const save = () => call('editor_save', typed());

  useEffect(() => {
    if (!shown) return undefined;
    const key = (e) => {
      if (e.ctrlKey && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
        if (s && s.save.button.enabled && !document.querySelector('.modal-back')) save();
      }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [shown, s, form, dirty]);

  if (!s) return html`<div class="empty">The Roster editor opens here.</div>`;
  if (!s.roster) {
    return html`<div class="empty ed-none"><div>
      <div class="big">${s.status.text}</div>
      <${Button} kind="primary" onClick=${onGoUpdate}>Go to the Update tab<//></div></div>`;
  }
  const m = s.modal;
  return html`<div class=${cls('ed', s.busy && 'busy')}>
    <div class="ed-bar">
      <div class="ed-roster"><span class="n">${s.roster.name}</span><${RegionTag} region=${s.roster.region}/></div>
      <${TextField} className="search" value=${s.query} placeholder="Find a player" disabled=${!s.loaded}
        onChange=${(t) => call('editor_search', t)} delay=${220}/>
      <${Button} onClick=${() => call('editor_new_player')} disabled=${!s.loaded}>New player<//>
      <${Button} onClick=${() => call('team_open')} disabled=${!s.team_tools.team}>Team...<//>
      <${Button} onClick=${() => call('uniforms_open')} disabled=${!s.team_tools.uniforms}
        title="The jerseys and the centre-ice logo of an NHL team">Jerseys and ice...<//>
      <${Button} onClick=${() => call('edits_open')}>My edits (${s.edits_count})<//>
    </div>
    <div class="ed-main">
      <${Teams} s=${s}/>
      <${Players} s=${s} onPick=${(id) => call('editor_player', id, typed())}/>
      <${PlayerCard} s=${s} form=${form} set=${set} setRating=${setRating} dirty=${dirty} onApply=${apply}/>
      ${!s.loaded && html`<div class="ed-loading"><div class="spinner"></div><div>${s.status.text}</div></div>`}
    </div>
    <div class="ed-save">
      <div class=${cls('ed-status', s.status.tone)} title=${s.status.text}>${s.status.text}</div>
      <${Segmented} options=${SAVE_MODES} value=${s.save.mode} disabled=${!s.save.mode_enabled}
        onChange=${(v) => call('editor_save_mode', v)}/>
      <${TextField} className="name" value=${s.save.name} disabled=${s.busy}
        onChange=${(t) => call('editor_name', t)}/>
      <${Button} kind="primary" big className="go" disabled=${!s.save.button.enabled} onClick=${save}
        title="Ctrl+S">${s.save.button.text}<//>
    </div>
    ${m && m.kind === 'team' && html`<${TeamWindow} key=${'team' + m.slot} m=${m}/>`}
    ${m && m.kind === 'edits' && html`<${EditsWindow} m=${m}/>`}
    ${uniforms && html`<${UniformsWindow} key=${'u' + uniforms.slot} u=${uniforms}/>`}
    ${equipment && html`<${EquipmentWindow} key=${'q' + equipment.who} q=${equipment}/>`}
  </div>`;
}
