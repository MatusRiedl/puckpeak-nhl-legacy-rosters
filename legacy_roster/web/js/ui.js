// The small parts the tabs are built from.
import { html, cls, useRef, useLayoutEffect, useState, useEffect } from './lib.js';

export function Button({ kind = 'ghost', small, big, block, disabled, onClick, title, className, children }) {
  return html`<button type="button" title=${title}
    class=${cls('btn', kind, small && 'small', big && 'big', block && 'block', className)}
    disabled=${disabled} onClick=${onClick}>${children}</button>`;
}

export function Toggle({ on, disabled, onChange, label }) {
  return html`<button type="button" role="switch" aria-checked=${!!on} aria-label=${label}
    class=${cls('toggle', on && 'on')} disabled=${disabled} onClick=${() => onChange(!on)}></button>`;
}

export function Checkbox({ on, disabled, onChange, children }) {
  return html`<div role="checkbox" aria-checked=${!!on} tabindex="0"
    class=${cls('check', on && 'on', disabled && 'disabled')}
    onClick=${() => !disabled && onChange(!on)}
    onKeyDown=${(e) => { if (!disabled && (e.key === ' ' || e.key === 'Enter')) { e.preventDefault(); onChange(!on); } }}>
    <span class="box"><svg viewBox="0 0 12 12"><path d="M2 6.5 5 9.2 10.2 3" fill="none" stroke="#fff" stroke-width="2"/></svg></span>
    ${children}
  </div>`;
}

// a choice of a few, with a thumb that slides to the one picked
export function Segmented({ options, value, disabled, onChange, className }) {
  const box = useRef(null);
  const [thumb, setThumb] = useState(null);
  useLayoutEffect(() => {
    const measure = () => {
      const el = box.current && box.current.querySelector('button.on');
      setThumb(el && el.offsetWidth ? { x: el.offsetLeft - 2, w: el.offsetWidth } : null);
    };
    measure();
    const watch = new ResizeObserver(measure);     // fonts arriving, a tab shown again
    watch.observe(box.current);
    return () => watch.disconnect();
  }, [value, options.map((o) => o.label).join('|')]);
  return html`<div ref=${box} class=${cls('seg', disabled && 'disabled', className)}>
    ${thumb && html`<span class="thumb" style=${{ width: thumb.w + 'px', transform: `translateX(${thumb.x}px)` }}></span>`}
    ${options.map((o) => html`<button type="button" key=${o.value} class=${o.value === value ? 'on' : ''}
        disabled=${disabled} onClick=${() => o.value !== value && onChange(o.value)}>${o.icon}${o.label}</button>`)}
  </div>`;
}

export function Card({ n, title, aside, grow, className, style, children }) {
  return html`<section class=${cls('card', grow && 'grow', className)} style=${style}>
    <header class="card-head">
      ${n != null && html`<span class="num">${n}</span>`}
      <span class="title">${title}</span>
      ${aside && html`<span class="aside">${aside}</span>`}
    </header>
    ${children}
  </section>`;
}

export function Flag({ region }) {
  if (region === 'EU') {
    const stars = [];
    for (let k = 0; k < 12; k++) {
      const a = (Math.PI * 2 * k) / 12;
      stars.push(html`<circle key=${k} cx=${9 + 3.6 * Math.sin(a)} cy=${6 - 3.6 * Math.cos(a)} r="0.65" fill="#ffcc00"/>`);
    }
    return html`<svg class="flag" viewBox="0 0 18 12"><rect width="18" height="12" fill="#003399"/>${stars}</svg>`;
  }
  const stripes = [];
  for (let k = 0; k < 13; k += 2) stripes.push(html`<rect key=${k} y=${(k * 12) / 13} width="18" height=${12 / 13} fill="#b22234"/>`);
  return html`<svg class="flag" viewBox="0 0 18 12"><rect width="18" height="12" fill="#fff"/>${stripes}
    <rect width="7.2" height=${(7 * 12) / 13} fill="#3c3b6e"/></svg>`;
}

export function RegionTag({ region }) {
  return html`<span class="chip region"><${Flag} region=${region}/>${region}</span>`;
}

// a path shortened in the middle by the layout itself: the end (file name) always shows
export function PathText({ path, unset }) {
  if (!path) return html`<div class="field path unset">${unset}</div>`;
  const cut = Math.max(path.lastIndexOf('\\'), path.lastIndexOf('/'));
  const head = cut > 0 ? path.slice(0, cut + 1) : '';
  const tail = cut > 0 ? path.slice(cut + 1) : path;
  return html`<div class="field path" title=${path}><span class="head">${head}</span><span class="tail">${tail}</span></div>`;
}

export function ProgressBar({ value, active, indeterminate }) {
  return html`<div class=${cls('progress', active && 'active', indeterminate && 'indeterminate')}
    role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow=${Math.round((value || 0) * 100)}>
    <div class="fill" style=${{ transform: `scaleX(${Math.max(0, Math.min(1, value || 0))})` }}></div>
    <div class="sweep"></div>
  </div>`;
}

// an input the player types in: Python's value is shown unless the player is typing
export function TextField({ value, disabled, onChange, delay = 250, className, placeholder, onEnter }) {
  const [text, setText] = useState(value || '');
  const typing = useRef(false);
  const timer = useRef(null);
  useEffect(() => { if (!typing.current) setText(value || ''); }, [value]);
  return html`<input class=${cls('field', className)} value=${text} disabled=${disabled} placeholder=${placeholder}
    spellcheck="false"
    onFocus=${() => { typing.current = true; }}
    onBlur=${() => { typing.current = false; clearTimeout(timer.current); if (text !== value) onChange(text); }}
    onKeyDown=${(e) => { if (e.key === 'Enter') { clearTimeout(timer.current); onChange(text); onEnter && onEnter(); } }}
    onInput=${(e) => { const t = e.target.value; setText(t); clearTimeout(timer.current);
      timer.current = setTimeout(() => onChange(t), delay); }}/>`;
}

export function Modal({ title, wide, full, onClose, buttons, children }) {
  useEffect(() => {
    const key = (e) => { if (e.key === 'Escape' && onClose) { e.stopPropagation(); onClose(); } };
    window.addEventListener('keydown', key, true);
    return () => window.removeEventListener('keydown', key, true);
  }, [onClose]);
  return html`<div class="modal-back" onMouseDown=${(e) => { if (e.target === e.currentTarget && onClose) onClose(); }}>
    <div class=${cls('modal', wide && 'wide', full && 'full')} role="dialog" aria-modal="true">
      <div class="m-head">${title}</div>
      <div class="m-body">${children}</div>
      ${buttons && html`<div class="m-buttons">${buttons}</div>`}
    </div>
  </div>`;
}
