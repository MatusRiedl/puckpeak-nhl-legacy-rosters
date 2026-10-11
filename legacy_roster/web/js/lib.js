// React (vendor/, MIT) with htm (vendor/, Apache-2.0): JSX-like templates without a build step.
import htm from '../vendor/htm.module.js';

const R = window.React;
export const html = htm.bind(R.createElement);
export const { useState, useEffect, useRef, useMemo, useCallback, useLayoutEffect, useSyncExternalStore, Fragment } = R;

export function cls(...parts) {
  return parts.filter(Boolean).join(' ');
}
