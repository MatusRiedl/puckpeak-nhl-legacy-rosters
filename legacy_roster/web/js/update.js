// The Update tab: 1 where RPCS3 is, 2 which roster, 3 what to update, 4 how to save.
import { html, cls, useEffect, useRef, useState } from './lib.js';
import { Button, Toggle, Checkbox, Segmented, Card, PathText, RegionTag, Flag, TextField } from './ui.js';
import { call } from './bridge.js';

function RpcsCard({ r, exp, busy, checkUpdates }) {
  const note = r.note;
  return html`<${Card} n="1" title="Where is RPCS3?" style=${{ '--i': 0 }}>
    <div class="card-body">
      <div class="row">
        <${PathText} path=${r.path} unset="Not set yet"/>
        <${Button} kind=${r.path ? 'ghost' : 'primary'} disabled=${!r.enabled} onClick=${() => call('pick_rpcs3')}>
          ${r.path ? 'Change' : r.find_label}</${Button}>
      </div>
      ${(note || r.running) && html`<div class=${cls('note', note && note.tone)}>
        ${r.running && html`<span class="pill" style=${{ marginRight: '8px' }}>RPCS3 is running</span>`}
        ${note && note.text}</div>`}
      ${r.needs_game && html`<div class="row" style=${{ marginTop: '10px' }}>
        <${Button} kind="primary" disabled=${busy} onClick=${() => call('pick_game', false)}>Pick the game (.iso)...</${Button}>
        <${Button} disabled=${busy} onClick=${() => call('pick_game', true)}>or its folder...</${Button}>
      </div>`}
      <${Checkbox} on=${exp.on} disabled=${busy} onChange=${(v) => call('set_export_only', v)}>Export only SYS-DATA roster</${Checkbox}>
      <div class="row">
        <${Checkbox} on=${checkUpdates} onChange=${(v) => call('set_check_updates', v)}>Look for a newer version when this program starts</${Checkbox}>
        <${Button} small disabled=${busy} onClick=${() => call('check_updates_now')}>Check for updates now</${Button}>
      </div>
    </div>
  </${Card}>`;
}

function RosterRow({ r, isNew }) {
  const usable = r.usable;
  return html`<div class=${cls('roster', r.selected && 'sel', !usable && 'off', isNew && 'appear')}
      role="radio" aria-checked=${r.selected} tabindex=${usable ? 0 : -1}
      onClick=${() => usable && call('select_roster', r.folder)}
      onKeyDown=${(e) => { if (usable && (e.key === ' ' || e.key === 'Enter')) { e.preventDefault(); e.stopPropagation(); call('select_roster', r.folder); } }}>
    <span class="dot"></span>
    <div class="main">
      <div class="name"><span class="n">${r.name}</span>${r.chip && html`<span class=${cls('chip', r.chip.kind)}>${r.chip.text}</span>`}</div>
      <div class="meta"><${RegionTag} region=${r.region}/><span class="t">${r.meta}</span></div>
      ${r.problem && html`<div class="problem">${r.problem}</div>`}
    </div>
    ${r.actions && html`<div class="acts" onClick=${(e) => e.stopPropagation()}>
      <${Button} small onClick=${() => call('open_roster_folder', r.folder)}>Open folder</${Button}>
      <${Button} small kind="danger" disabled=${!r.delete_enabled} onClick=${() => call('ask_delete', r.folder)}>Delete</${Button}>
    </div>`}
  </div>`;
}

function RosterCard({ s }) {
  const seen = useRef(null);
  const list = useRef(null);
  const folders = s.rosters.map((r) => r.folder);
  // rows that are new since the last look slide in; the first fill does not animate row by row
  const fresh = seen.current ? new Set(folders.filter((f) => !seen.current.has(f))) : new Set();
  useEffect(() => { seen.current = new Set(folders); });
  useEffect(() => {
    const el = list.current && list.current.querySelector('.roster.sel');
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [s.selected, folders.join('|')]);
  const exp = s.export;
  return html`<${Card} n="2" title="Which roster should be updated?" grow style=${{ '--i': 1, minHeight: '150px' }}>
    <div class="card-body fill">
      ${exp.on ? html`<div>
          <div class=${cls('note', exp.tone)} style=${{ marginTop: 0, marginBottom: '10px' }}>${exp.text}</div>
          <${Button} kind="primary" disabled=${s.busy} onClick=${() => call('pick_export_file')}>Pick the roster file (SYS-DATA)...</${Button}>
        </div>` : html`
        ${s.fresh.length > 0 && html`<div class="fresh">Start fresh:
          ${s.fresh.map((f) => html`<${Button} small key=${f.folder} disabled=${s.busy}
              onClick=${() => call('select_roster', f.folder)}><${Flag} region=${f.region}/>${f.label}</${Button}>`)}</div>`}
        ${s.rosters.length ? html`<div class="scroll" ref=${list}><div class="list" role="radiogroup">
            ${s.rosters.map((r) => html`<${RosterRow} key=${r.folder} r=${r} isNew=${fresh.has(r.folder)}/>`)}
          </div></div>` : html`<div class="empty">${s.empty}</div>`}`}
    </div>
  </${Card}>`;
}

function StepRow({ row }) {
  return html`<div class=${cls('step', row.on && 'on', row.restoring && 'restoring')}>
    <div class="main">
      <div class="title">${row.title}</div>
      <div class="sub">${row.sub}</div>
      ${row.warn && html`<div class="warn">${row.warn}</div>`}
      ${row.hint && html`<div class="hint">${row.hint}</div>`}
    </div>
    ${row.restore && html`<${Button} small kind=${row.restoring ? 'amber' : 'ghost'} disabled=${!row.restore_enabled}
        title=${row.restoring ? 'Press again to keep it as it is' : 'Put this part back as the game had it, in the next save'}
        onClick=${() => call('toggle_restore', row.key)}>${row.restoring ? 'Restoring' : 'Restore'}</${Button}>`}
    <${Toggle} on=${row.on} disabled=${!row.enabled} label=${row.title} onChange=${(v) => call('set_step', row.key, v)}/>
  </div>`;
}

function StepsCard({ s }) {
  return html`<${Card} n="3" title="What should be updated?" grow style=${{ '--i': 2 }}>
    <div class="card-body fill">
      <div class="scroll"><div class="list">${s.steps.map((row) => html`<${StepRow} key=${row.key} row=${row}/>`)}</div></div>
    </div>
    <div class="card-foot">
      ${s.later && html`<div class="later">${s.later}</div>`}
      ${s.restore_pictures.shown && html`<div><${Button} small disabled=${!s.restore_pictures.enabled}
          onClick=${() => call('remove_photos')}>Restore the game's own pictures</${Button}></div>`}
      ${s.restore_all.shown && html`<${Button} kind="primary" big block disabled=${!s.restore_all.enabled}
          onClick=${() => call('restore_default')}>Restore default: rosters, calendar and pictures</${Button}>`}
    </div>
  </${Card}>`;
}

function Result({ result }) {
  // the box keeps showing the last result while it closes
  const [shown, setShown] = useState(result);
  useEffect(() => { if (result) setShown(result); }, [result]);
  const r = result || shown;
  return html`<div class=${cls('result-wrap', result && 'open')} style=${{ '--i': 3 }}
      onTransitionEnd=${(e) => { if (e.target === e.currentTarget && !result) setShown(null); }}>
    <div class="inner">${r && html`<div class=${cls('result', r.good ? 'good' : 'bad')}>
      <div class="r-head"><div class="r-title">${r.title}</div>
        <button class="x" title="Close" onClick=${() => call('result_action', 'close')}>✕</button></div>
      <div class="r-body selectable">
        ${r.lines.map((line, k) => html`<p key=${k}>${line}</p>`)}
        ${r.items.length > 0 && html`<dl class="items">${r.items.map(([t, text], k) => html`
          <dt key=${'t' + k}>${t}</dt><dd key=${'d' + k}>${text}</dd>`)}</dl>`}
      </div>
      ${r.buttons.length > 0 && html`<div class="r-buttons">${r.buttons.map((b) => html`
        <${Button} small key=${b.action} kind=${b.action === 'start_rpcs3' ? 'primary' : 'ghost'}
          onClick=${() => call('result_action', b.action)}>${b.label}</${Button}>`)}</div>`}
      ${r.dim && html`<div class="dim">${r.dim}</div>`}
    </div>`}</div>
  </div>`;
}

function SaveCard({ s }) {
  const v = s.save;
  const go = () => call('start');
  return html`<${Card} n="4" title="Save" style=${{ '--i': 4 }}>
    <div class="card-body">
      ${v.mode_shown && html`<${Segmented} value=${v.mode} disabled=${!v.mode_enabled}
          options=${[{ value: 'update', label: 'Update this roster' }, { value: 'new', label: 'Save as a new roster' }]}
          onChange=${(m) => call('set_save_mode', m)}/>`}
      <div class="save-row">
        <${TextField} value=${v.name} disabled=${!v.name_enabled} onChange=${(t) => call('set_name', t)}/>
        <${Button} kind="primary" big className=${cls('go', s.busy && 'working')} disabled=${!v.button.enabled}
          onClick=${go}>${v.button.text}</${Button}>
      </div>
      ${v.save_for && html`<div class="save-row"><span class="savefor">Save for</span>
        <${Segmented} value=${v.save_for.value} disabled=${!v.save_for.enabled}
          options=${v.save_for.options.map((o) => ({ value: o, label: o,
            icon: o === 'EU + NA' ? html`<${Flag} region="EU"/><${Flag} region="NA"/>` : html`<${Flag} region=${o}/>` }))}
          onChange=${(x) => call('set_save_for', x)}/></div>`}
      <div class="small-note" style=${{ marginTop: '8px' }}>${v.note}</div>
    </div>
  </${Card}>`;
}

export function UpdateTab({ s }) {
  if (!s) return null;
  return html`<div class="columns">
    <div class="col">
      <${RpcsCard} r=${s.rpcs3} exp=${s.export} busy=${s.busy} checkUpdates=${s.check_updates}/>
      <${StepsCard} s=${s}/>
    </div>
    <div class="col">
      <${RosterCard} s=${s}/>
      <${Result} result=${s.result}/>
      <${SaveCard} s=${s}/>
    </div>
  </div>`;
}
