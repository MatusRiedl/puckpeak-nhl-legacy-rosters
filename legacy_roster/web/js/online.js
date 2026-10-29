// The Play online tab: your online account, the one-press setup, a lobby of two by code, and what to press in the game.
// Python (app/online.py) holds everything; this page shows the `online` slice and calls online_*.
import { html, cls, useState } from './lib.js';
import { call } from './bridge.js';
import { Button, Card, Segmented, TextField } from './ui.js';

function Mark({ ok, label, note }) {
  return html`<div class=${cls('om', ok ? 'ok' : 'no')}><span class="dot">${ok ? '✓' : '•'}</span>
    <span class="lab">${label}</span>${note && html`<span class="small-note">${note}</span>`}</div>`;
}

function AccountCard({ s }) {
  return html`<${Card} title="Your online account" style=${{ '--i': 0 }}>
    <div class="card-body">
      ${s.account
        ? html`<div class="row on-account"><span class="who">${s.account}</span><span class="small-note">RPCN name from RPCS3</span></div>`
        : html`<div class="small-note">${s.no_account}</div>`}
      <div class="row on-actions"><${Button} small disabled=${!!s.busy} onClick=${() => call('online_check')}>Check again<//></div>
    </div>
  <//>`;
}

function SetupCard({ s }) {
  const m = s.marks;
  return html`<${Card} title="Set up" style=${{ '--i': 1 }}>
    <div class="card-body">
      <${Mark} ok=${m.online} label="Online entry in RPCS3"/>
      <${Mark} ok=${m.patched} label="Game patch (32 teams, year 2026)"/>
      <${Mark} ok=${s.server === true} label="Puck Peak server" note=${s.server === false ? 'not reachable' : null}/>
      <${Mark} ok=${s.build != null && !s.build_old} label="RPCS3 version" note=${s.build != null ? 'build ' + s.build : 'not seen yet'}/>
      <div class="row on-actions">
        <${Button} kind="primary" disabled=${!!s.busy || !s.account || m.game === 'open'}
          onClick=${() => call('online_setup')}>${m.ready ? 'Set up again' : 'Set up online'}<//>
        ${m.game === 'open' && html`<span class="small-note">Close RPCS3 first.</span>`}
      </div>
      <div class="small-note">Online play needs the game patch: Set up puts it in for you, after asking. The roster is the host's:
        it is copied to you when you join. Your own rosters are not touched.</div>
    </div>
  <//>`;
}

function Member({ m, me, progress }) {
  const ok = m.roster_ok && m.patch_ok;
  const flag = !m.roster_ok ? 'needs the roster' : !m.patch_ok ? 'other game patch' : (m.role === 'host' ? 'brings the roster' : 'same roster');
  return html`<div class=${cls('om-member', me && 'me')}>
    <span class="who">${m.name}</span><span class="role">${m.role === 'host' ? 'host' : 'guest'}</span>
    <span class=${cls('om-flag', ok ? 'ok' : 'no')} title=${m.patch ? 'game patch: ' + m.patch : ''}>${flag}</span>
    <span class="prog">${m.ready ? 'Ready · ' : ''}${progress[m.progress] || ''}</span>
  </div>`;
}

function LobbyCard({ s }) {
  const [text, setText] = useState('');
  const lob = s.lobby, ok = s.state !== 'no-rpcs3' && s.state !== 'no-account' && s.state !== 'not-set-up';
  if (!lob) {
    return html`<${Card} title="Play a friend" style=${{ '--i': 2 }}>
      <div class="card-body">
        <div class="small-note">One of you makes a lobby. Public lobbies are in the list below for anybody; a private one is joined with its code. Then both press Ready.</div>
        <div class=${cls('om-bring', s.bring_why && 'no')}>${s.bring_why ? s.bring_why : 'You bring: ' + s.bring + ' (picked in Setup)'}</div>
        <div class="row on-actions">
          <${Segmented} options=${[{ value: 'private', label: 'Private' }, { value: 'public', label: 'Public' }]}
            value=${s.public ? 'public' : 'private'} disabled=${!!s.busy} onChange=${(v) => call('online_public', v === 'public')}/>
          <${Button} kind="primary" disabled=${!ok || !!s.busy || !!s.bring_why || !!s.build_old} onClick=${() => call('online_create')}>Make a lobby<//>
        </div>
        ${s.build_old && html`<div class="om-why">${s.build_old}</div>`}
        <div class="small-note">Joining copies your friend's roster into your Puck Peak Online save (a backup is kept).</div>
        <div class="row on-actions">
          <${TextField} className="on-code" value=${text} placeholder="Lobby code from a friend" onChange=${setText}
            onEnter=${() => call('online_join', text)}/>
          <${Button} disabled=${!ok || !!s.busy || !text.trim()} onClick=${() => call('online_join', text)}>Join<//>
        </div>
      </div>
    <//>`;
  }
  const mine = lob.members.find((m) => m.name === s.account);
  return html`<${Card} title="Your lobby" aside=${lob.state} style=${{ '--i': 2 }}>
    <div class="card-body">
      <div class="row on-codebox"><span class="on-code-big selectable">${s.code}</span>
        <${Button} small onClick=${() => navigator.clipboard && navigator.clipboard.writeText(s.code)}>Copy<//>
        <span class="small-note">${s.public && s.role === 'host' ? 'Listed for everybody. You can also send this code.' : 'Tell your friend this code.'}</span></div>
      <div class="om-members">${lob.members.map((m) => html`<${Member} key=${m.name} m=${m} me=${m.name === s.account} progress=${s.progress}/>`)}</div>
      ${s.brought && html`<div class="small-note">You bring: ${s.brought}</div>`}
      ${lob.members.length < 2 && html`<div class="small-note">Waiting for your friend to join...</div>`}
      <div class="small-note">The match is the game's standard online match: 5 minute periods, NHL rules.</div>
      ${lob.reason && html`<div class="om-why">${lob.reason}</div>`}
      ${s.hint && html`<div class="om-why">${s.hint}${s.guest_problem && html` <${Button} small onClick=${() => call('tab', 'patch')}>Open Game patch<//>`}</div>`}
      ${s.build_note && html`<div class="om-why">${s.build_note.text}</div>`}
      ${s.game_note && html`<div class="om-why">${s.game_note.text}</div>`}
      <div class="row on-actions">
        ${!s.launched && html`<${Button} kind="primary" disabled=${!!s.busy || lob.members.length < 2 || (!!s.guest_problem && !(mine && mine.ready))}
          onClick=${() => call('online_ready', !(mine && mine.ready))}>${mine && mine.ready ? 'Not ready' : 'Ready'}<//>`}
        <${Button} disabled=${!!s.busy} onClick=${() => call('online_leave')}>Leave<//>
      </div>
    </div>
  <//>`;
}

function age(seconds) {
  if (seconds < 60) return 'just now';
  const m = Math.round(seconds / 60);
  return m < 60 ? m + ' min' : Math.round(m / 60) + ' h';
}

function OpenRow({ r, ok, busy }) {
  return html`<div class=${cls('om-open', !r.joinable && 'no')}>
    <span class="who" title=${r.host}>${r.host}</span>
    <span class="ros" title=${r.roster_name}>${r.roster_name || 'roster'}</span>
    <span class="meta">${age(r.age_seconds)} · ${r.members} of ${r.max}</span>
    <${Button} small kind=${r.joinable ? 'primary' : 'ghost'} disabled=${!ok || busy || !r.joinable}
      onClick=${() => call('online_join', r.code)}>Join<//>
    ${r.why && html`<span class="why">${r.why}</span>`}
    ${r.warn && html`<span class="why">${r.warn}</span>`}
  </div>`;
}

function OpenCard({ s }) {
  const ok = s.state === 'ready';
  return html`<${Card} title="Open lobbies" aside=${s.open.length ? String(s.open.length) : null} grow style=${{ '--i': 3 }}>
    <div class="card-body fill"><div class="scroll">
      ${s.open_error && html`<div class="om-why">${s.open_error}</div>`}
      ${!s.open_error && !s.open.length && html`<div class="small-note">${ok
        ? 'Nobody is waiting right now. Make a public lobby and your friends will see it here.'
        : 'Set up online first to see the lobbies.'}</div>`}
      ${s.open.map((r) => html`<${OpenRow} key=${r.code} r=${r} ok=${ok} busy=${!!s.busy}/>`)}
      <div class="row on-actions"><${Button} small disabled=${!ok} onClick=${() => call('online_list')}>Refresh<//>
        <span class="small-note">The list refreshes by itself.</span></div>
    </div></div>
  <//>`;
}

function StepsCard({ s }) {
  return html`<${Card} title=${s.launched ? 'Now, in the game' : 'Then, in the game'} grow style=${{ '--i': 3 }}>
    <div class="card-body fill"><div class="scroll">
      ${s.why && html`<div class="om-why">${s.why}</div>`}
      <ol class="om-steps">${s.steps.map((t, k) => html`<li key=${k}>${t}</li>`)}</ol>
      <div class="small-note">The game does the rest once both of you are in the session.</div>
    </div></div>
  <//>`;
}

function HelpCard() {
  return html`<${Card} title="How it works" grow style=${{ '--i': 3 }}>
    <div class="card-body fill"><div class="scroll patch-info">
      <ul>
        <li>Make your online account once in RPCS3. This tab reads only its name.</li>
        <li>Press Set up online. It adds the online part of the game patch.</li>
        <li>Pick the roster you want to play with in Setup. The one who makes the lobby brings it; the other gets a copy.</li>
        <li>Online play needs the game patch. Set up puts it in for you, after asking.</li>
        <li>One of you makes a lobby (private: send the code; public: it shows in the list), the other joins, both press Ready.</li>
        <li>RPCS3 starts by itself on both PCs. Follow the short list of buttons to press in the game.</li>
      </ul>
    </div></div>
  <//>`;
}

export function OnlineTab({ s }) {
  if (!s) return null;
  return html`<div class="columns online">
    <div class="col">
      <${AccountCard} s=${s}/>
      ${s.state === 'no-rpcs3'
        ? html`<${Card} title="Set up" style=${{ '--i': 1 }}><div class="card-body"><div class="small-note">Pick RPCS3 in Setup first.</div></div><//>`
        : html`<${SetupCard} s=${s}/>`}
      ${s.note && html`<div class=${cls('om-note', s.note.tone)}>${s.note.text}</div>`}
      ${s.busy && html`<div class="small-note">${s.busy}</div>`}
    </div>
    <div class="col">
      <${LobbyCard} s=${s}/>
      ${s.lobby ? (s.steps.length ? html`<${StepsCard} s=${s}/>` : html`<${HelpCard}/>`) : html`<${OpenCard} s=${s}/>`}
    </div>
  </div>`;
}
