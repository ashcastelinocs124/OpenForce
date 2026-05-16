export function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    value >= 0.8
      ? "bg-emerald-100 text-emerald-800"
      : value >= 0.5
        ? "bg-amber-100 text-amber-800"
        : "bg-rose-100 text-rose-800";
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {pct}% confidence
    </span>
  );
}
