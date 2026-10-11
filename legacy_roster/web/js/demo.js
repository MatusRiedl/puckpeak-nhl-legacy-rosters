// The page in a normal browser, without Python (tools/window_shot.py): ?fixture=<file.json> is what the
// program would have pushed (slices, log, meta). Buttons do nothing here; the calls show in the console.
export async function makeApi(params) {
  const file = params.get('fixture') || '__fixture.json';
  const reply = await fetch(file);
  if (!reply.ok) throw new Error(`no ${file}: start tools/window_shot.py`);
  const message = await reply.json();
  const api = { ready: () => message };
  return new Proxy(api, {
    get: (target, name) => target[name] || ((...args) => { console.log('call', name, ...args); return null; }),
  });
}
