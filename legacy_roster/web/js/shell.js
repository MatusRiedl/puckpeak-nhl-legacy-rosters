// The frame around the tabs: the arena, the header, the tab switch, the Help bar, the details.
import { html, cls, useRef, useLayoutEffect, useState, useEffect } from './lib.js';
import { ProgressBar, Button, Modal } from './ui.js';
import { call } from './bridge.js';
import { useLog } from './store.js';

export function Backdrop() {
  // the glossy white band with its red edges over the top of the game's menus
  return html`<div class="backdrop" aria-hidden="true">
    <div class="lights"></div>
    <svg viewBox="0 0 1000 150" preserveAspectRatio="none">
      <defs>
        <linearGradient id="band" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#fff" stop-opacity=".0"/>
          <stop offset=".18" stop-color="#fff" stop-opacity=".55"/>
          <stop offset=".5" stop-color="#fff" stop-opacity=".22"/>
          <stop offset=".82" stop-color="#fff" stop-opacity=".55"/>
          <stop offset="1" stop-color="#fff" stop-opacity=".0"/>
        </linearGradient>
        <linearGradient id="red" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#c8102e" stop-opacity="0"/>
          <stop offset=".2" stop-color="#e2233f" stop-opacity=".9"/>
          <stop offset=".8" stop-color="#e2233f" stop-opacity=".9"/>
          <stop offset="1" stop-color="#c8102e" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <path d="M0,30 Q500,-34 1000,30" fill="none" stroke="url(#red)" stroke-width="1.6"/>
      <path d="M0,40 Q500,-22 1000,40 L1000,50 Q500,-8 0,50 Z" fill="url(#band)"/>
      <path d="M0,54 Q500,-2 1000,54" fill="none" stroke="url(#red)" stroke-width="2.2"/>
    </svg>
    <div class="floor"></div>
  </div>`;
}

export function Header({ meta }) {
  return html`<header class="header">
    <img class="logo" src="img/logo.png" alt="Puck Peak" draggable="false" onClick=${() => call('open_site')}/>
    <div class="tagline">${meta.tagline} · <a onClick=${() => call('open_site')}>${meta.site_label}</a></div>
    <div class="titleline"><b>LEGACY ROSTER UPDATER</b><span class="sep">|</span><span>NHL Legacy Edition on RPCS3</span>
      <span class="sep">|</span><span>version ${meta.version}</span></div>
  </header>`;
}

export function TabBar({ tabs, tab, onTab }) {
  const box = useRef(null);
  const [thumb, setThumb] = useState(null);
  useLayoutEffect(() => {
    const measure = () => {
      const el = box.current && box.current.querySelector('button.on');
      if (el) setThumb({ x: el.offsetLeft - 2, w: el.offsetWidth });
    };
    measure();
    const watch = new ResizeObserver(measure);
    watch.observe(box.current);
    return () => watch.disconnect();
  }, [tab]);
  const index = tabs.findIndex((t) => t.id === tab);
  const step = (d) => onTab(tabs[(index + d + tabs.length) % tabs.length].id);
  return html`<nav class="tabs">
    <span class="keycap" title="Ctrl+Page Up" onClick=${() => step(-1)}>L1</span>
    <div class="tabset" ref=${box}>
      ${thumb && html`<span class="thumb" style=${{ width: thumb.w + 'px', transform: `translateX(${thumb.x}px)` }}></span>`}
      ${tabs.map((t) => html`<button type="button" key=${t.id} class=${t.id === tab ? 'on' : ''} onClick=${() => onTab(t.id)}>${t.label}</button>`)}
    </div>
    <span class="keycap" title="Ctrl+Page Down" onClick=${() => step(1)}>R1</span>
  </nav>`;
}

export function HelpBar({ status, progress, detailsOpen, onDetails, hint }) {
  const value = progress ? progress.value : 0;
  const shown = progress && (progress.active || value > 0);
  return html`<footer class="helpbar">
    <${ProgressBar} value=${value} active=${progress && progress.active} indeterminate=${progress && progress.indeterminate}/>
    <span class="pct">${shown ? Math.round(value * 100) + '%' : ''}</span>
    <span class=${cls('status', status && status.tone)} title=${status && status.text}>${status ? status.text : ''}</span>
    <span class="keys">
      ${hint && html`<span class="key"><span class="keycap">Enter</span>${hint}</span>`}
      <span class="key" onClick=${onDetails}><span class="keycap">D</span>${detailsOpen ? 'Hide details' : 'Details'}</span>
    </span>
  </footer>`;
}

export function Details({ open, onClose }) {
  const log = useLog();
  const box = useRef(null);
  const follow = useRef(true);
  useEffect(() => {
    const el = box.current;
    if (el && open && follow.current) el.scrollTop = el.scrollHeight;
  }, [log.version, open]);
  return html`<div class=${cls('details', open && 'open')} aria-hidden=${!open}>
    <div class="d-head">DETAILS<span class="sp"></span>
      <${Button} small onClick=${() => call('open_error_log')}>Error log</${Button}>
      <${Button} small onClick=${onClose}>Close</${Button}></div>
    <pre ref=${box} onScroll=${(e) => { const el = e.target; follow.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 8; }}
      >${log.lines.join('\n')}</pre>
  </div>`;
}

// a question from Python (Delete, Restore default...), in the look of the game's Help box
export function Question({ dialog, onAnswer }) {
  if (!dialog) return null;
  const cancel = dialog.buttons.find((b) => b.style === 'plain') || (dialog.buttons.length === 1 ? dialog.buttons[0] : null);
  const kinds = { primary: 'pick', danger: 'danger', plain: 'ghost' };
  return html`<${Modal} title=${dialog.title} onClose=${cancel ? () => onAnswer(dialog.id, cancel.answer) : null}
    buttons=${dialog.buttons.map((b, k) => html`<${Button} key=${k} kind=${kinds[b.style] || 'ghost'} big
      onClick=${() => onAnswer(dialog.id, b.answer)}>${b.label}</${Button}>`)}>
    ${dialog.lines.map((line, k) => html`<p key=${k}>${line}</p>`)}
  </${Modal}>`;
}
