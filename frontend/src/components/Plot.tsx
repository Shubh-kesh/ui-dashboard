import { useEffect, useRef } from 'react';
import Plotly from 'plotly.js-dist-min';
import type { Config, Data, Layout } from 'plotly.js';

interface PlotProps {
  data: Data[];
  layout?: Partial<Layout>;
  config?: Partial<Config>;
  className?: string;
  /** Test hook: rendered as a data attribute so tests can find the chart. */
  testId?: string;
}

/** Thin React wrapper around plotly.js (kept dependency-light). */
export default function Plot({ data, layout, config, className, testId }: PlotProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    void Plotly.react(ref.current, data, layout ?? {}, {
      responsive: true,
      displaylogo: false,
      ...config,
    });
  }, [data, layout, config]);

  useEffect(() => {
    const el = ref.current;
    return () => {
      if (el) Plotly.purge(el);
    };
  }, []);

  return <div ref={ref} className={className} data-testid={testId} />;
}
