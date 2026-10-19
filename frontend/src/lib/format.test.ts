import { describe, expect, it } from 'vitest';
import { addDaysISO, fmtNumber, fmtPct, fmtSeconds } from './format';

describe('format helpers', () => {
  it('formats numbers with separators', () => {
    expect(fmtNumber(1234567)).toBe('1,234,567');
  });

  it('renders a dash for nullish numbers', () => {
    expect(fmtNumber(null)).toBe('—');
    expect(fmtNumber(undefined)).toBe('—');
  });

  it('formats percentages with digits', () => {
    expect(fmtPct(87.654)).toBe('87.7%');
    expect(fmtPct(null)).toBe('—');
  });

  it('formats seconds', () => {
    expect(fmtSeconds(0.5)).toBe('0.500s');
    expect(fmtSeconds(null)).toBe('—');
  });

  it('adds days across month boundaries', () => {
    expect(addDaysISO('2026-10-12', -6)).toBe('2026-10-06');
    expect(addDaysISO('2026-03-01', -1)).toBe('2026-02-28');
  });
});
