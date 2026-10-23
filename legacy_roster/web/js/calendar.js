// The Calendar tab: a month page (Monday to Sunday) with the picked team's games, a day's games, the team's list of
// games; with "My season" on, the results of the player's own Season or Be a GM save (app/calendar.py, read only).
import { html, cls } from './lib.js';
import { Button, Segmented, Toggle, Card } from './ui.js';
import { call } from './bridge.js';
import { Code } from './rail.js';

const WEEK = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function Day({ d, teamMode }) {
  const m = d.mine;
  const title = (d.allstar ? 'All-Star Game. ' : '') + (d.count ? `${d.count} ${d.count === 1 ? 'game' : 'games'}` : 'No games');
  return html`<button type="button" class=${cls('cal-day', d.out && 'out', d.today && 'today', d.sel && 'sel',
      teamMode && m && (m.home ? 'home' : 'away'), !d.count && !d.allstar && 'none')}
      onClick=${() => call('calendar_day', d.date)} title=${title}>
    <span class="n">${d.n}${d.allstar && html`<span class="star" title="All-Star Game">★</span>`}</span>
    ${teamMode && m ? html`<span class="g"><span class="at">${m.home ? 'vs' : '@'}</span> ${m.vs}</span>
        ${m.result && html`<span class=${cls('r', m.result.tone)}>${m.result.text}</span>`}`
      : d.count > 0 && html`<span class=${cls('cnt', !teamMode && 'big')}>${d.count}<i>${d.count === 1 ? ' game' : ' games'}</i></span>`}
  </button>`;
}

function SeasonSwitch({ season }) {
  if (!season || !season.available) return null;
  return html`<label class="cal-season" title=${season.note || ''}><${Toggle} on=${season.on} gold label="My season"
      onChange=${(v) => call('calendar_season', v)}/>
    <span>${season.on ? season.label : 'My season'}</span></label>`;
}

function Month({ s }) {
  const teamMode = s.mode === 'team';
  return html`<section class="card grow cal-month">
    <header class="card-head cal-head">
      <button class="cal-arrow" disabled=${!s.can_prev} title="The month before" onClick=${() => call('calendar_month', -1)}>‹</button>
      <span class="title cal-title">${s.title}</span>
      <button class="cal-arrow" disabled=${!s.can_next} title="The month after" onClick=${() => call('calendar_month', 1)}>›</button>
      <${Button} small onClick=${() => call('calendar_today')}>Today<//>
      <span class="sp"></span>
      <${Segmented} value=${s.mode} onChange=${(m) => call('calendar_mode', m)}
        options=${[{ value: 'team', label: `${s.team.code}'s games` }, { value: 'league', label: `All ${s.league} games` }]}/>
    </header>
    <div class="cal-grid" style=${{ '--weeks': s.weeks.length }}>
      ${WEEK.map((w) => html`<div key=${w} class="cal-wd">${w}</div>`)}
      ${s.weeks.flat().map((d) => html`<${Day} key=${d.date} d=${d} teamMode=${teamMode}/>`)}
    </div>
    <footer class="cal-foot">
      ${teamMode ? html`<span><span class="key home">vs</span> home game</span><span><span class="key away">@</span> away game</span>`
        : html`<span>${s.count_note}</span>`}
      ${s.league_note && html`<span class="faint">${s.league_note}</span>`}
      <span class="sp"></span>
      <${SeasonSwitch} season=${s.season}/>
    </footer>
  </section>`;
}

function TeamCard({ s }) {
  const r = s.record;
  return html`<section class="card cal-team">
    <div class="cal-team-head"><${Code} team=${s.team}/><div class="t">${s.team.name}</div></div>
    <div class="tiles">
      ${r ? html`<div class="tile"><b>${r.text}</b><span>${r.pts} pts · ${r.gp} GP</span></div>
          <div class="tile" title=${r.place_text}><b>${(r.place_text || '').split(' in ')[0]}</b><span>${r.division}</span></div>`
        : html`<div class="tile"><b>${s.summary.gp}</b><span>games</span></div>
          <div class="tile"><b>${s.summary.home}</b><span>home</span></div>
          <div class="tile"><b>${s.summary.away}</b><span>away</span></div>`}
    </div>
    ${s.summary.next && html`<div class="cal-next">Next: <b>${s.summary.next}</b></div>`}
    ${s.season && s.season.on && s.season.note && html`<div class="small-note gold-note">${s.season.note}</div>`}
  </section>`;
}

function DayCard({ day }) {
  return html`<section class="card cal-daycard">
    <header class="card-head"><span class="title">${day.title}</span>
      <span class="aside">${day.games.length ? `${day.games.length} ${day.games.length === 1 ? 'game' : 'games'}` : 'No games'}</span>
      <button class="x" title="Close" onClick=${() => call('calendar_day', null)}>✕</button></header>
    <div class="scroll"><div class="cal-games">
      ${day.games.map((g, k) => html`<div key=${k} class=${cls('cal-match', g.mine && 'mine')}>
        <${Code} team=${g.away} small/><span class="at">@</span><${Code} team=${g.home} small/>
        <span class="names" title=${`${g.away.name} at ${g.home.name}`}>${g.label ? g.label + ': ' : ''}${g.away.name} at ${g.home.name}</span>
        ${g.score && html`<span class="score">${g.score}</span>`}
      </div>`)}
      ${!day.games.length && html`<div class="empty small">No games this day.</div>`}
    </div></div>
  </section>`;
}

export function Standings({ st }) {
  return html`<section class="card cal-stand">
    <header class="card-head"><span class="title">${st.division}</span>${st.conference && html`<span class="aside">${st.conference}</span>`}</header>
    <div class="scroll"><table class="mini"><thead><tr><th></th><th>GP</th><th>W</th><th>L</th><th>OTL</th><th>PTS</th></tr></thead>
      <tbody>${st.rows.map((r) => html`<tr key=${r.slot} class=${r.mine ? 'mine' : ''}>
        <td><${Code} team=${{ code: r.code, colours: r.colours, name: r.code }} small/></td><td>${r.gp}</td><td>${r.w}</td><td>${r.l}</td>
        <td>${r.otl}</td><td><b>${r.pts}</b></td></tr>`)}</tbody></table></div>
  </section>`;
}

function GameList({ s }) {
  return html`<${Card} title="Games" aside=${`${s.summary.gp} · ${s.summary.home} home, ${s.summary.away} away`} grow className="cal-list">
    <div class="scroll"><div class="cal-months">
      ${s.months.map((m) => html`<div key=${m.ym} class="cal-mgroup">
        <div class="cal-mlabel">${m.label}</div>
        ${m.games.map((g) => html`<button type="button" key=${g.date} class=${cls('cal-row', g.sel && 'sel', g.past && 'past')}
            onClick=${() => call('calendar_day', g.date)}>
          <span class="d">${g.label}</span><span class=${cls('ha', g.home ? 'home' : 'away')}>${g.home ? 'vs' : '@'}</span>
          <span class="vs">${g.vs}${g.playoffs && html`<span class="faint"> playoffs</span>`}</span>
          ${g.result && html`<span class=${cls('r', g.result.tone)}>${g.result.text}</span>`}
        </button>`)}
      </div>`)}
    </div></div>
  <//>`;
}

export function CalendarTab({ s }) {
  if (!s) return null;
  if (s.why) {
    return html`<div class="why card">${s.team && html`<${Code} team=${s.team}/>`}<p>${s.why}</p>
      ${s.team && html`<${SeasonSwitch} season=${s.season}/>`}</div>`;
  }
  return html`<div class="cal">
    <${Month} s=${s}/>
    <div class="cal-side">
      ${s.mode === 'team' && html`<${TeamCard} s=${s}/>`}
      ${s.day && html`<${DayCard} day=${s.day}/>`}
      ${s.standings && !s.day && html`<${Standings} st=${s.standings}/>`}
      ${s.mode === 'team' ? html`<${GameList} s=${s}/>`
        : !s.day && html`<div class="card cal-hint"><p>Click a day to see its games.</p></div>`}
    </div>
  </div>`;
}
