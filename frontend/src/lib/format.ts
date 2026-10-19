export function fmtNumber(n: number | null | undefined): string {
  return n == null ? '—' : n.toLocaleString();
}

export function fmtPct(v: number | null | undefined, digits = 1): string {
  return v == null ? '—' : `${v.toFixed(digits)}%`;
}

export function fmtSeconds(v: number | null | undefined, digits = 3): string {
  return v == null ? '—' : `${v.toFixed(digits)}s`;
}

export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export function daysAgoISO(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}
