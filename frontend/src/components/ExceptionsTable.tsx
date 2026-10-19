interface Props {
  rows: Record<string, unknown>[];
}

function cell(value: unknown): string {
  if (value === null || value === undefined) return '';
  return String(value);
}

export default function ExceptionsTable({ rows }: Props) {
  if (rows.length === 0) {
    return (
      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-800">Exceptions</h2>
        <p className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          No exceptions in the selected range.
        </p>
      </section>
    );
  }
  const columns = [...new Set(rows.flatMap((r) => Object.keys(r)))];
  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-slate-800">
        Exceptions <span className="text-sm font-normal text-slate-500">({rows.length})</span>
      </h2>
      <div className="max-h-96 overflow-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm" data-testid="exceptions-table">
          <thead className="sticky top-0 bg-slate-100 text-left text-slate-600">
            <tr>
              {columns.map((c) => (
                <th key={c} className="px-3 py-2 font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-slate-100">
                {columns.map((c) => (
                  <td key={c} className="px-3 py-2 text-slate-700">
                    {cell(r[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
