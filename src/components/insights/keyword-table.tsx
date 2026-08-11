"use client";

import * as React from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/lib/types";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

/* Keyword performance table — sortable columns:
   Keyword · Hits · Avg score · Approval rate.
   - Hits = number of conversations whose matchedKeywords array contains the term
   - Avg score = mean score across matched conversations
   - Approval rate = approved / total matched */

interface KeywordStat {
  keyword: string;
  hits: number;
  avgScore: number;
  approvalRate: number;
}

function buildStats(convos: Conversation[]): KeywordStat[] {
  const map = new Map<string, { hits: number; scoreSum: number; approved: number }>();
  for (const c of convos) {
    const seen = new Set<string>();
    for (const kw of c.matchedKeywords) {
      if (seen.has(kw)) continue;
      seen.add(kw);
      const cur = map.get(kw) ?? { hits: 0, scoreSum: 0, approved: 0 };
      cur.hits += 1;
      cur.scoreSum += c.score;
      if (c.status === "approved") cur.approved += 1;
      map.set(kw, cur);
    }
  }
  const rows: KeywordStat[] = [];
  for (const [keyword, v] of map.entries()) {
    rows.push({
      keyword,
      hits: v.hits,
      avgScore: v.hits === 0 ? 0 : v.scoreSum / v.hits,
      approvalRate: v.hits === 0 ? 0 : (v.approved / v.hits) * 100,
    });
  }
  return rows;
}

const columnHelper = createColumnHelper<KeywordStat>();

// Columns array inferred as `(ColumnDef<KeywordStat, string> | ColumnDef<KeywordStat, number>)[]`.
// Declaring the type explicitly as `ColumnDef<KeywordStat>[]` triggers a v8
// variance issue with the second type param, so we let TS infer.
const columns = [
  columnHelper.accessor("keyword", {
    header: "Keyword",
    cell: (info) => (
      <span className="font-medium text-text">{info.getValue()}</span>
    ),
  }),
  columnHelper.accessor("hits", {
    header: "Hits",
    cell: (info) => (
      <span className="font-mono tabular-nums text-text">
        {info.getValue()}
      </span>
    ),
  }),
  columnHelper.accessor("avgScore", {
    header: "Avg score",
    cell: (info) => {
      const v = info.getValue();
      return (
        <span
          className={cn(
            "font-mono tabular-nums",
            v >= 60
              ? "text-primary"
              : v >= 40
                ? "text-warning"
                : "text-text-muted",
          )}
        >
          {Math.round(v)}
        </span>
      );
    },
  }),
  columnHelper.accessor("approvalRate", {
    header: "Approval rate",
    cell: (info) => {
      const v = info.getValue();
      return (
        <span
          className={cn(
            "font-mono tabular-nums",
            v >= 30 ? "text-success" : v > 0 ? "text-text-muted" : "text-risk",
          )}
        >
          {Math.round(v)}%
        </span>
      );
    },
  }),
];

function SortHeader({
  label,
  column,
}: {
  label: string;
  column: { getIsSorted: () => false | "asc" | "desc"; toggleSorting: () => void };
}) {
  const sorted = column.getIsSorted();
  const Icon = sorted === "asc" ? ArrowUp : sorted === "desc" ? ArrowDown : ChevronsUpDown;
  return (
    <button
      type="button"
      onClick={() => column.toggleSorting()}
      className="inline-flex items-center gap-1 text-xs font-medium text-text-muted hover:text-text transition-colors"
      aria-label={`Sort by ${label}, currently ${sorted ? sorted : "unsorted"}`}
    >
      {label}
      <Icon className="h-3 w-3" aria-hidden />
    </button>
  );
}

export function KeywordTable({ convos }: { convos: Conversation[] }) {
  const data = React.useMemo(() => buildStats(convos), [convos]);
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: "hits", desc: true },
  ]);
  // TanStack Table is designed to return a stable table instance whose
  // own methods are not referentially stable — the React Compiler skips
  // memoization here, which is expected and safe.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (data.length === 0) {
    return (
      <p className="text-sm text-text-muted py-8 text-center">
        No keyword matches in this range.
      </p>
    );
  }

  return (
    <div
      role="region"
      aria-label="Keyword performance table, sortable"
      className="max-h-[360px] overflow-y-auto rounded-md border border-border"
    >
      <Table>
        <TableHeader className="sticky top-0 bg-surface z-10">
          {table.getHeaderGroups().map((hg) => (
            <TableRow key={hg.id}>
              {hg.headers.map((header) => {
                const col = header.column;
                return (
                  <TableHead key={header.id} className="px-3">
                    {header.isPlaceholder ? null : (
                      <SortHeader
                        label={String(col.columnDef.header)}
                        column={col}
                      />
                    )}
                  </TableHead>
                );
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => (
            <TableRow key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id} className="px-3 py-2 text-sm">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
