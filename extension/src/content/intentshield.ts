// ─── intentshield.ts ──────────────────────────────────────────────────────────
// IntentShield: interaction-safety layer for IntentLock.
//
// Responsibilities:
//  1. Dwell-to-click — show a progress ring at the cursor position, fire a
//     synthesised click only when the dwell timer completes.
//  2. High-impact confirmation — for submit / delete / purchase elements, show a
//     two-step prompt before activating.
//  3. Pause / Resume — disables all activation while paused; cursor still moves.
//
// Limitations (honestly documented):
//  • High-impact heuristics rely on keyword matching and ARIA roles.
//    Custom UIs may use none of these signals and will not be caught.
//  • Dwell targets use the element under the virtualised cursor coordinate,
//    which may differ from what the pointer-events layer would hit if the
//    overlay is in the way.
// ──────────────────────────────────────────────────────────────────────────────

// ── State ────────────────────────────────────────────────────────────────────

let isPaused = false;
let dwellHost: HTMLDivElement | null = null;
let dwellShadow: ShadowRoot | null = null;
let dwellRafId: number | null = null;
let dwellStartMs = 0;
let dwellX = 0;
let dwellY = 0;
const DWELL_MS = 1200; // ms to hold before activating

// ── Keyword heuristics ───────────────────────────────────────────────────────

const HIGH_IMPACT_PATTERNS = [
  /\bdelete\b/i,
  /\bremove\b/i,
  /\bpurchase\b/i,
  /\bbuy\b/i,
  /\bsubmit\b/i,
  /\bsend\b/i,
  /\bconfirm\b/i,
  /\bcheckout\b/i,
  /\bplace order\b/i,
  /\bpay\b/i,
];

function isHighImpact(el: Element): boolean {
  const text = `${(el as HTMLElement).innerText ?? ''} ${el.getAttribute('aria-label') ?? ''} ${el.getAttribute('title') ?? ''}`.toLowerCase();
  return HIGH_IMPACT_PATTERNS.some(p => p.test(text));
}

// ── Dwell ring shadow DOM ─────────────────────────────────────────────────────

function ensureDwellUI() {
  if (dwellHost) return;
  dwellHost = document.createElement('div');
  dwellHost.id = 'intentlock-dwell-host';
  Object.assign(dwellHost.style, {
    position:      'fixed',
    top:           '0',
    left:          '0',
    width:         '0',
    height:        '0',
    overflow:      'visible',
    pointerEvents: 'none',
    zIndex:        '2147483644',
  });
  document.documentElement.appendChild(dwellHost);
  dwellShadow = dwellHost.attachShadow({ mode: 'open' });

  dwellShadow.innerHTML = `
    <style>
      .dwell-ring {
        position: fixed;
        width: 44px;
        height: 44px;
        pointer-events: none;
        transform: translate(-50%, -50%) rotate(-90deg);
      }
      .dwell-bg { fill: none; stroke: rgba(0,0,0,0.15); stroke-width: 4; }
      .dwell-arc { fill: none; stroke: #007bff; stroke-width: 4; stroke-linecap: round;
                   stroke-dasharray: 113; stroke-dashoffset: 113; transition: none; }
      .dwell-cancel {
        position: fixed;
        background: rgba(220,53,69,0.9);
        color: #fff;
        font: bold 11px sans-serif;
        padding: 2px 7px;
        border-radius: 10px;
        pointer-events: none;
        white-space: nowrap;
        transform: translate(-50%, 28px);
      }
    </style>
    <svg class="dwell-ring" viewBox="0 0 44 44">
      <circle class="dwell-bg" cx="22" cy="22" r="18"/>
      <circle class="dwell-arc" cx="22" cy="22" r="18"/>
    </svg>
    <div class="dwell-cancel">Hold to click — voice "cancel" to abort</div>
  `;
}

function updateDwellRing(progress: number, x: number, y: number) {
  if (!dwellShadow) return;
  const circumference = 113;
  const arc = dwellShadow.querySelector<SVGCircleElement>('.dwell-arc');
  const ring = dwellShadow.querySelector<SVGElement>('.dwell-ring');
  const cancel = dwellShadow.querySelector<HTMLElement>('.dwell-cancel');
  if (arc) arc.style.strokeDashoffset = String(circumference * (1 - progress));
  if (ring) { ring.style.left = `${x}px`; ring.style.top = `${y}px`; }
  if (cancel) { cancel.style.left = `${x}px`; cancel.style.top = `${y}px`; }
}

function hideDwellUI() {
  if (dwellShadow) {
    const ring = dwellShadow.querySelector<SVGElement>('.dwell-ring');
    const cancel = dwellShadow.querySelector<HTMLElement>('.dwell-cancel');
    if (ring) ring.style.display = 'none';
    if (cancel) cancel.style.display = 'none';
  }
  if (dwellRafId !== null) { cancelAnimationFrame(dwellRafId); dwellRafId = null; }
}

function showDwellUI(x: number, y: number) {
  if (!dwellShadow) return;
  const ring = dwellShadow.querySelector<SVGElement>('.dwell-ring');
  const cancel = dwellShadow.querySelector<HTMLElement>('.dwell-cancel');
  if (ring)   ring.style.display = 'block';
  if (cancel) cancel.style.display = 'block';
  updateDwellRing(0, x, y);
}

// ── Confirmation overlay ──────────────────────────────────────────────────────

let confirmHost: HTMLDivElement | null = null;
let confirmShadow: ShadowRoot | null = null;

function showConfirmation(label: string, onConfirm: () => void) {
  dismissConfirmation();

  confirmHost = document.createElement('div');
  confirmHost.id = 'intentlock-confirm-host';
  Object.assign(confirmHost.style, {
    position: 'fixed',
    top: '0', left: '0', width: '100%', height: '100%',
    zIndex: '2147483643',
    pointerEvents: 'auto',
  });
  document.documentElement.appendChild(confirmHost);
  confirmShadow = confirmHost.attachShadow({ mode: 'open' });

  confirmShadow.innerHTML = `
    <style>
      .backdrop { position:fixed; inset:0; background:rgba(0,0,0,0.45); display:flex; align-items:center; justify-content:center; }
      .card { background:#fff; border-radius:10px; padding:24px 28px; max-width:340px; text-align:center; box-shadow:0 8px 32px rgba(0,0,0,0.25); }
      h3 { margin:0 0 8px; font-size:16px; color:#333; }
      p  { margin:0 0 18px; font-size:13px; color:#555; }
      .label { font-weight:bold; color:#007bff; }
      .row { display:flex; gap:10px; justify-content:center; }
      button { border:none; padding:9px 22px; border-radius:7px; font:600 13px sans-serif; cursor:pointer; }
      .confirm-btn { background:#dc3545; color:#fff; }
      .cancel-btn  { background:#e9ecef; color:#333; }
      .badge { font-size:11px; color:#888; margin-top:12px; }
    </style>
    <div class="backdrop">
      <div class="card">
        <h3>⚠️ Confirm Action</h3>
        <p>You are about to activate:<br/><span class="label">${label.slice(0, 80)}</span></p>
        <p style="font-size:11px;color:#888;">This action is classified as potentially high-impact by keyword heuristics. Custom UIs may not be caught.</p>
        <div class="row">
          <button class="confirm-btn" id="il-confirm">Confirm</button>
          <button class="cancel-btn"  id="il-cancel">Cancel</button>
        </div>
      </div>
    </div>
  `;

  confirmShadow.getElementById('il-confirm')!.addEventListener('click', () => {
    dismissConfirmation();
    onConfirm();
  });
  confirmShadow.getElementById('il-cancel')!.addEventListener('click', () => {
    dismissConfirmation();
  });
}

function dismissConfirmation() {
  confirmHost?.remove();
  confirmHost = null;
  confirmShadow = null;
}

// ── Public API ────────────────────────────────────────────────────────────────

export function pause()  { isPaused = true;  hideDwellUI(); dismissConfirmation(); }
export function resume() { isPaused = false; }
export function isPausedState() { return isPaused; }

/** Start a dwell-click at viewport fraction (x,y 0..1). */
export function startDwell(xFrac: number, yFrac: number) {
  if (isPaused) return;
  ensureDwellUI();

  const px = xFrac * window.innerWidth;
  const py = yFrac * window.innerHeight;

  hideDwellUI();
  dwellX = px;
  dwellY = py;
  dwellStartMs = performance.now();
  showDwellUI(px, py);

  function tick() {
    const elapsed = performance.now() - dwellStartMs;
    const progress = Math.min(elapsed / DWELL_MS, 1);
    updateDwellRing(progress, dwellX, dwellY);

    if (progress < 1) {
      dwellRafId = requestAnimationFrame(tick);
    } else {
      hideDwellUI();
      fireDwellClick(px, py);
    }
  }
  dwellRafId = requestAnimationFrame(tick);
}

export function cancelDwell() { hideDwellUI(); }

function fireDwellClick(px: number, py: number) {
  if (isPaused) return;

  // Find element under cursor
  const el = document.elementFromPoint(px, py);
  if (!el) return;

  const label = (el as HTMLElement).innerText?.trim().slice(0, 100) ?? el.tagName;

  if (isHighImpact(el)) {
    showConfirmation(label, () => (el as HTMLElement).click());
  } else {
    (el as HTMLElement).click();
  }
}

/** Voice-initiated click by coordinate. */
export function voiceClick(xFrac: number, yFrac: number) {
  if (isPaused) return;
  fireDwellClick(xFrac * window.innerWidth, yFrac * window.innerHeight);
}

export function cleanup() {
  hideDwellUI();
  dismissConfirmation();
  dwellHost?.remove(); dwellHost = null; dwellShadow = null;
}
