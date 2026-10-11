/**
 * 1€ Filter (One Euro Filter) for High-Speed, Jitter-Free Pointer Tracking.
 * 
 * Reference: Casiez, G., Roussel, N. and Vogel, D. (2012).
 * "1€ Filter: A Simple Speed-based Low-pass Filter for Jittery and Laggy Input."
 * Proceedings of the SIGCHI Conference on Human Factors in Computing Systems (CHI '12), pp. 2527-2530.
 *
 * Characteristics:
 * - Low speed (hovering / clicking): cutoff frequency drops to minCutoff (~1.0Hz) to eliminate micro-jitter and tremors.
 * - High speed (sweeping across screen): cutoff frequency dynamically rises (beta * |speed|) for instantaneous, zero-lag tracking.
 */

export class LowPassFilter {
  private y: number | null = null;
  private s: number | null = null;

  filter(value: number, alpha: number): number {
    if (this.y === null) {
      this.s = value;
      this.y = value;
      return value;
    }
    this.s = alpha * value + (1.0 - alpha) * (this.s as number);
    this.y = value;
    return this.s;
  }

  hasLast(): boolean {
    return this.s !== null;
  }

  last(): number {
    return this.s ?? 0;
  }

  reset(): void {
    this.y = null;
    this.s = null;
  }
}

export class OneEuroFilter {
  private minCutoff: number;
  private beta: number;
  private dCutoff: number;
  private xFilter = new LowPassFilter();
  private dxFilter = new LowPassFilter();
  private lastTime: number | null = null;

  /**
   * @param minCutoff Cutoff frequency in Hz at zero speed (lower = smoother when still, default: 1.0)
   * @param beta Speed coefficient (higher = faster response when moving, default: 0.025)
   * @param dCutoff Cutoff frequency in Hz for derivative calculation (default: 1.0)
   */
  constructor(minCutoff = 1.0, beta = 0.025, dCutoff = 1.0) {
    this.minCutoff = minCutoff;
    this.beta = beta;
    this.dCutoff = dCutoff;
  }

  private alpha(cutoff: number, dt: number): number {
    const tau = 1.0 / (2 * Math.PI * cutoff);
    return 1.0 / (1.0 + tau / dt);
  }

  filter(value: number, timestamp = performance.now()): number {
    if (this.lastTime === null) {
      this.lastTime = timestamp;
      return this.xFilter.filter(value, 1.0);
    }

    const dt = Math.max(1e-3, (timestamp - this.lastTime) / 1000.0);
    this.lastTime = timestamp;

    const prevX = this.xFilter.last();
    const dx = (value - prevX) / dt;
    const edx = this.dxFilter.filter(dx, this.alpha(this.dCutoff, dt));

    const cutoff = this.minCutoff + this.beta * Math.abs(edx);
    return this.xFilter.filter(value, this.alpha(cutoff, dt));
  }

  reset(): void {
    this.xFilter.reset();
    this.dxFilter.reset();
    this.lastTime = null;
  }
}

export class OneEuroFilter2D {
  private xFilter: OneEuroFilter;
  private yFilter: OneEuroFilter;

  constructor(minCutoff = 1.0, beta = 0.025, dCutoff = 1.0) {
    this.xFilter = new OneEuroFilter(minCutoff, beta, dCutoff);
    this.yFilter = new OneEuroFilter(minCutoff, beta, dCutoff);
  }

  filter(x: number, y: number, timestamp = performance.now()): { x: number; y: number } {
    return {
      x: this.xFilter.filter(x, timestamp),
      y: this.yFilter.filter(y, timestamp),
    };
  }

  reset(): void {
    this.xFilter.reset();
    this.yFilter.reset();
  }
}
