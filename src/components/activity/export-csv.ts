import type { ActivityEntry } from "@/lib/types";

/* ============================================================
   exportActivityCsv — turn filtered activity rows into a CSV
   download. Filename format: signal-activity-YYYYMMDD.csv
   ============================================================ */

function csvEscape(value: string | undefined): string {
  if (value === undefined || value === null) return "";
  const needsQuote = /[",\n\r]/.test(value);
  const escaped = value.replace(/"/g, '""');
  return needsQuote ? `"${escaped}"` : escaped;
}

function todayStamp(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}${m}${day}`;
}

export function buildActivityCsv(rows: ActivityEntry[]): string {
  const header = [
    "Timestamp",
    "Actor",
    "Action",
    "Item",
    "Before",
    "After",
  ];
  const lines = [header.join(",")];
  for (const r of rows) {
    lines.push(
      [
        csvEscape(r.timestamp),
        csvEscape(r.actor),
        csvEscape(r.action),
        csvEscape(r.item),
        csvEscape(r.before),
        csvEscape(r.after),
      ].join(","),
    );
  }
  return lines.join("\r\n");
}

export function exportActivityCsv(rows: ActivityEntry[]): void {
  const csv = buildActivityCsv(rows);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `signal-activity-${todayStamp()}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoke on next tick so the download has time to start.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
