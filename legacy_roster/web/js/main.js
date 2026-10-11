// The window: the arena, the header, the two tabs, the Help bar.
import { html, cls, useState, useEffect } from './lib.js';
import { connect, call, params } from './bridge.js';
import { useSlice, useMeta, on } from './store.js';
import { Backdrop, Header, TabBar, HelpBar, Details, Question } from './shell.js';
import { UpdateTab } from './update.js';
import { EditorTab } from './editor.js';

const TABS = [{ id: 'update', label: 'Update' }, { id: 'editor', label: 'Roster editor' }];
const SHORT = 720;          // window heights below this fold the big logo (768-line laptops)

function useShort() {
  const [short, setShort] = useState(window.innerHeight < SHORT);
  useEffect(() => {
    const fit = () => setShort(window.innerHeight < SHORT);
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, []);
  return short;
}

function typingIn(target) {
  return target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable);
}

function App() {
  const meta = useMeta();
  const update = useSlice('update');
  const editor = useSlice('editor');
  const [tab, setTab] = useState(params.get('tab') || 'update');
  const [from, setFrom] = useState(null);
  const [details, setDetails] = useState(params.has('details'));
  const short = useShort();
  const [enter, setEnter] = useState(true);       // the cards rise in once, when the window opens
  useEffect(() => {
    if (!meta.version) return undefined;
    const t = setTimeout(() => setEnter(false), 1400);
    return () => clearTimeout(t);
  }, [meta.version]);

  const pickTab = (id) => {
    if (id === tab) return;
    setFrom(TABS.findIndex((t) => t.id === id) > TABS.findIndex((t) => t.id === tab) ? 'from-right' : 'from-left');
    setTab(id);
    call('tab', id);
  };

  useEffect(() => on('details', (p) => setDetails(p && p.open !== undefined ? p.open : true)), []);
  useEffect(() => on('focus_tab', (p) => pickTab(p.tab)), [tab]);
  useEffect(() => { if (meta.version && tab !== 'update') call('tab', tab); }, [meta.version]);

  useEffect(() => {
    const key = (e) => {
      if (e.ctrlKey && (e.key === 'PageUp' || e.key === 'PageDown')) {
        e.preventDefault();
        const i = TABS.findIndex((t) => t.id === tab);
        pickTab(TABS[(i + (e.key === 'PageDown' ? 1 : TABS.length - 1)) % TABS.length].id);
        return;
      }
      if (e.key === 'F5' || (e.ctrlKey && (e.key === 'r' || e.key === 'R'))) { e.preventDefault(); return; }
      if (typingIn(e.target) || document.querySelector('.modal-back')) return;
      if ((e.key === 'd' || e.key === 'D') && !e.ctrlKey && !e.altKey) setDetails((d) => !d);
      else if (e.key === 'Escape' && details) setDetails(false);
      else if (e.key === 'Enter' && tab === 'update' && update && update.save.button.enabled
               && !(e.target && e.target.closest && e.target.closest('button, [role=radio], [role=checkbox]'))) call('start');
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [tab, details, update]);

  if (!meta.version) return html`<div class="app"><${Backdrop}/></div>`;
  // the editor's own line is in its save bar; the Help bar repeats it only while the editor works
  const status = tab === 'editor' && editor && !(update && update.busy)
    ? (editor.busy ? editor.status : { text: editor.loaded ? 'Pick a team, then a player.   Ctrl+S saves.' : '', tone: 'info' })
    : update && update.status;
  const progress = update && (update.busy || !(editor && editor.busy)) ? update.progress
    : { value: 0, active: false, indeterminate: true };
  const hint = tab === 'update' && update && update.save.button.enabled ? update.save.button.text : null;
  return html`<div class=${cls('app', enter && 'enter', short && 'compact')}>
    <${Backdrop}/>
    <${Header} meta=${meta}/>
    <${TabBar} tabs=${TABS} tab=${tab} onTab=${pickTab}/>
    <main class="stage">
      <section class=${cls('pane', tab === 'update' && from)} hidden=${tab !== 'update'}><${UpdateTab} s=${update}/></section>
      <section class=${cls('pane', tab === 'editor' && from)} hidden=${tab !== 'editor'}>
        <${EditorTab} s=${editor} shown=${tab === 'editor'} onGoUpdate=${() => pickTab('update')}/></section>
    </main>
    <${Details} open=${details} onClose=${() => setDetails(false)}/>
    <${HelpBar} status=${status} progress=${progress} detailsOpen=${details} onDetails=${() => setDetails(!details)} hint=${hint}/>
    <${Question} dialog=${update && update.dialog} onAnswer=${(id, a) => call('answer', id, a)}/>
  </div>`;
}

// the window never navigates away: links open in the player's browser (through Python)
document.addEventListener('dragover', (e) => e.preventDefault());
document.addEventListener('drop', (e) => e.preventDefault());
document.addEventListener('contextmenu', (e) => { if (!typingIn(e.target) && !e.target.closest('.selectable, pre')) e.preventDefault(); });
if (params.has('still')) document.documentElement.classList.add('still');

window.ReactDOM.createRoot(document.getElementById('root')).render(html`<${App}/>`);
connect().catch((err) => {
  document.getElementById('root').textContent = 'The window could not start: ' + err;
});
