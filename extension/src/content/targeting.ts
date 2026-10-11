// ─── targeting.ts ─────────────────────────────────────────────────────────────
// Scans the page for visible interactive elements, renders numbered overlay
// badges in an isolated shadow root, and provides select-by-number / name APIs.
//
// Design notes:
//  • All badges live inside a shadow root so they cannot be styled by the page.
//  • The host element uses pointer-events:none so it never consumes page clicks.
//  • We observe DOM mutations and re-scan on navigation / page changes.
// ──────────────────────────────────────────────────────────────────────────────

const INTERACTIVE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'textarea:not([disabled])',
  'select:not([disabled])',
  '[role="button"]:not([aria-disabled="true"])',
  '[role="link"]',
  '[role="menuitem"]',
  '[role="option"]',
  '[role="tab"]',
  '[role="checkbox"]',
  '[role="radio"]',
  '[role="textbox"]',
  '[role="combobox"]',
  '[contenteditable="true"]',
].join(',');

interface TargetEntry {
  el: Element;
  label: string;
  n: number;
}

let shadowHost: HTMLDivElement | null = null;
let shadowRoot: ShadowRoot | null = null;
let entries: TargetEntry[] = [];
let mutationObs: MutationObserver | null = null;
let isEnabled = false;
let scrollRafId: number | null = null;

// ── Helpers ──────────────────────────────────────────────────────────────────

function getLabel(el: Element): string {
  // Priority: aria-label → aria-labelledby → title → placeholder → visible text
  const ariaLabel = el.getAttribute('aria-label')?.trim();
  if (ariaLabel) return ariaLabel;

  const labelledBy = el.getAttribute('aria-labelledby');
  if (labelledBy) {
    const t = document.getElementById(labelledBy)?.textContent?.trim();
    if (t) return t;
  }

  const title = el.getAttribute('title')?.trim();
  if (title) return title;

  const placeholder = (el as HTMLInputElement).placeholder?.trim();
  if (placeholder) return placeholder;

  // Associated <label> for form fields
  const id = el.getAttribute('id');
  if (id) {
    const assoc = document.querySelector(`label[for="${CSS.escape(id)}"]`)?.textContent?.trim();
    if (assoc) return assoc;
  }

  // Visible text content (truncated)
  const text = (el as HTMLElement).innerText?.trim().replace(/\s+/g, ' ');
  if (text) return text.slice(0, 40);

  // Fallback
  const tag = el.tagName.toLowerCase();
  const type = el.getAttribute('type') ?? '';
  return `${tag}${type ? `[${type}]` : ''}`;
}

function isVisible(el: Element): boolean {
  const rect = el.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return false;
  if (rect.bottom < 0 || rect.top > window.innerHeight) return false;
  if (rect.right < 0 || rect.left > window.innerWidth) return false;
  const style = window.getComputedStyle(el);
  if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') return false;
  return true;
}

// ── Shadow DOM setup ─────────────────────────────────────────────────────────

function ensureShadow() {
  if (shadowHost) return;
  shadowHost = document.createElement('div');
  shadowHost.id = 'intentlock-targeting-host';
  Object.assign(shadowHost.style, {
    position:      'absolute',
    top:           '0',
    left:          '0',
    width:         '100%',
    height:        '100%',
    overflow:      'visible',
    pointerEvents: 'none',
    zIndex:        '2147483645',
  });
  document.documentElement.appendChild(shadowHost);
  shadowRoot = shadowHost.attachShadow({ mode: 'open' });

  // Inject badge styles into shadow root
  const style = document.createElement('style');
  style.textContent = `
    .il-badge {
      position: fixed;
      min-width: 20px;
      height: 20px;
      padding: 0 5px;
      border-radius: 4px;
      background: #007bff;
      color: #fff;
      font: bold 11px/20px -apple-system, sans-serif;
      text-align: center;
      pointer-events: none;
      box-shadow: 0 1px 4px rgba(0,0,0,0.4);
      white-space: nowrap;
      user-select: none;
      transform: translate(0, -100%);
    }
  `;
  shadowRoot.appendChild(style);
}

// ── Core scan ────────────────────────────────────────────────────────────────

function clearBadges() {
  if (!shadowRoot) return;
  shadowRoot.querySelectorAll('.il-badge').forEach(b => b.remove());
}

export function scan() {
  if (!isEnabled) return;
  clearBadges();
  entries = [];

  const candidates = Array.from(document.querySelectorAll(INTERACTIVE_SELECTOR));
  let n = 1;

  for (const el of candidates) {
    if (!isVisible(el)) continue;

    const rect = el.getBoundingClientRect();
    const label = getLabel(el);

    const badge = document.createElement('div');
    badge.className = 'il-badge';
    badge.textContent = String(n);
    badge.title = label;
    Object.assign(badge.style, {
      left: `${window.scrollX + rect.left + 2}px`,
      top:  `${window.scrollY + rect.top}px`,
    });

    shadowRoot!.appendChild(badge);
    entries.push({ el, label, n });
    n++;

    // Cap at 50 to keep the overlay readable
    if (n > 50) break;
  }
}

// ── Public API ───────────────────────────────────────────────────────────────

export function enableTargeting() {
  isEnabled = true;
  ensureShadow();
  scan();

  // Re-scan on scroll (throttled to one rAF per event burst)
  // capture:true catches scroll events on nested scrollable containers
  const onScrollOrResize = () => {
    if (scrollRafId) return;
    scrollRafId = requestAnimationFrame(() => {
      scan();
      scrollRafId = null;
    });
  };
  window.addEventListener('scroll', onScrollOrResize, { capture: true, passive: true });
  window.addEventListener('resize', onScrollOrResize, { passive: true });

  // Watch for DOM changes and re-scan
  mutationObs = new MutationObserver(() => {
    if (scrollRafId) return;
    scrollRafId = requestAnimationFrame(() => { scan(); scrollRafId = null; });
  });
  mutationObs.observe(document.body, { childList: true, subtree: true, attributes: false });

  // Store listeners so we can remove them in disableTargeting
  (window as any).__ilScrollHandler = onScrollOrResize;
}

export function disableTargeting() {
  isEnabled = false;
  clearBadges();
  entries = [];
  mutationObs?.disconnect();
  mutationObs = null;
  if (scrollRafId) { cancelAnimationFrame(scrollRafId); scrollRafId = null; }
  // Remove scroll/resize listeners
  const handler = (window as any).__ilScrollHandler;
  if (handler) {
    window.removeEventListener('scroll', handler, { capture: true });
    window.removeEventListener('resize', handler);
    delete (window as any).__ilScrollHandler;
  }
  shadowHost?.remove();
  shadowHost = null;
  shadowRoot = null;
}

/** Select element by badge number. Returns a result object. */
export function selectByNumber(n: number): { success: boolean; label?: string; ambiguous?: boolean } {
  const entry = entries.find(e => e.n === n);
  if (!entry) return { success: false };
  activateElement(entry.el);
  return { success: true, label: entry.label };
}

/** Select element by name (case-insensitive contains match). */
export function selectByName(name: string): { success: boolean; label?: string; ambiguous?: boolean; alternatives?: string[] } {
  const needle = name.toLowerCase();
  const matches = entries.filter(e => e.label.toLowerCase().includes(needle));
  if (matches.length === 0) return { success: false };
  if (matches.length === 1) {
    activateElement(matches[0].el);
    return { success: true, label: matches[0].label };
  }
  // Ambiguous: return numbered alternatives
  return {
    success: false,
    ambiguous: true,
    alternatives: matches.map(e => `${e.n}: ${e.label}`),
  };
}

function activateElement(el: Element) {
  const tag = el.tagName.toLowerCase();
  const type = (el as HTMLInputElement).type?.toLowerCase() ?? '';

  // Focus text inputs without submitting
  if (tag === 'input' && !['submit', 'button', 'reset', 'checkbox', 'radio'].includes(type)) {
    (el as HTMLElement).focus();
    return;
  }
  if (tag === 'textarea' || (el as HTMLElement).isContentEditable) {
    (el as HTMLElement).focus();
    return;
  }
  // Everything else: click
  (el as HTMLElement).click();
}
