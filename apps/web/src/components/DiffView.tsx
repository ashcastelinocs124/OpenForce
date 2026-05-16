export function DiffView({
  before,
  after,
}: {
  before: Record<string, unknown>;
  after: Record<string, unknown>;
}) {
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)]));
  if (keys.length === 0) {
    return <p className="text-sm italic text-slate-500">No fields in diff.</p>;
  }
  return (
    <table className="w-full text-sm">
      <thead className="text-slate-500">
        <tr>
          <th className="text-left font-medium">Field</th>
          <th className="text-left font-medium">Before</th>
          <th className="text-left font-medium">After</th>
        </tr>
      </thead>
      <tbody>
        {keys.map((k) => {
          const b = before[k];
          const a = after[k];
          const changed = JSON.stringify(b) !== JSON.stringify(a);
          return (
            <tr key={k} className={changed ? "bg-amber-50" : ""}>
              <td className="py-1 pr-3 font-mono text-xs">{k}</td>
              <td className="py-1 pr-3 text-rose-700 line-through">
                {b == null ? "—" : String(b)}
              </td>
              <td className="py-1 text-emerald-700">{a == null ? "—" : String(a)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
