export function fmt$(n: number) {
  return "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

export function pct(n: number) {
  return (n * 100).toFixed(1) + "%";
}

export function fmtDate(s: string, opts?: Intl.DateTimeFormatOptions) {
  return new Date(s).toLocaleDateString(
    undefined,
    opts ?? { month: "short", day: "numeric", year: "numeric" }
  );
}
