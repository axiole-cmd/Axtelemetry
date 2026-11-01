// Substituto mínimo da biblioteca "chance" (só o que o gremlins.js usa), com semente fixa.
export default class Chance {
  constructor(seed) { this.s = (seed || 1) >>> 0; }
  random() { let t = (this.s += 0x6D2B79F5); t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }
  floating(o = {}) { const min = o.min ?? 0, max = o.max ?? 1; return min + this.random() * (max - min); }
  integer(o = {}) { const min = o.min ?? -1000, max = o.max ?? 1000; return Math.floor(min + this.random() * (max - min + 1)); }
  natural(o = {}) { return this.integer({ min: o.min ?? 0, max: o.max ?? 1000 }); }
  bool(o = {}) { return this.random() * 100 < (o.likelihood ?? 50); }
  character() { const c = 'abcdefghijklmnopqrstuvwxyz0123456789 '; return c[this.integer({ min: 0, max: c.length - 1 })]; }
  pick(a) { return a[this.integer({ min: 0, max: a.length - 1 })]; }
  email() { return 'teste' + this.natural() + '@exemplo.com'; }
  sentence() { return Array.from({ length: 6 }, () => this.pick(['volta', 'pista', 'freio', 'curva', 'setup', 'teste'])).join(' ') + '.'; }
}
