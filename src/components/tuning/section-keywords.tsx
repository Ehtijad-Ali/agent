"use client";

import * as React from "react";
import { useSignalStore } from "@/stores/signal-store";
import type { KeywordRule, MatchType, TuningConfig } from "@/lib/types";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Search, Plus, Trash2, ClipboardPaste, Download } from "lucide-react";
import { cn } from "@/lib/utils";

const clone = (c: TuningConfig): TuningConfig => JSON.parse(JSON.stringify(c));

/** SectionKeywords — editable positive-keyword table with search, inline
 *  add, bulk paste import (phrase-match, weight 10), CSV export, and
 *  duplicate detection (rose border + "Duplicate of row N" tooltip). */
export function SectionKeywords() {
  const config = useSignalStore((s) => s.config);
  const draftConfig = useSignalStore((s) => s.draftConfig);
  const setDraftConfig = useSignalStore((s) => s.setDraftConfig);
  const active = draftConfig ?? config;

  const [query, setQuery] = React.useState("");
  const [newTerm, setNewTerm] = React.useState("");
  const [pasteOpen, setPasteOpen] = React.useState(false);
  const [pasteText, setPasteText] = React.useState("");

  const { firstOccurrence, duplicates } = React.useMemo(() => {
    const first = new Map<string, number>();
    const dupes = new Set<number>();
    active.keywords.forEach((kw, i) => {
      const key = kw.term.toLowerCase().trim();
      if (!first.has(key)) first.set(key, i);
      else dupes.add(i);
    });
    return { firstOccurrence: first, duplicates: dupes };
  }, [active.keywords]);

  const filtered = React.useMemo(() => {
    if (!query.trim()) return active.keywords;
    const q = query.toLowerCase();
    return active.keywords.filter((k) => k.term.toLowerCase().includes(q));
  }, [active.keywords, query]);

  const editRow = (id: string, patch: Partial<KeywordRule>) =>
    setDraftConfig({
      ...clone(active),
      keywords: active.keywords.map((k) => (k.id === id ? { ...k, ...patch } : k)),
    });

  const deleteRow = (id: string) =>
    setDraftConfig({
      ...clone(active),
      keywords: active.keywords.filter((k) => k.id !== id),
    });

  function addTerm() {
    const t = newTerm.trim();
    if (!t) return;
    setDraftConfig({
      ...clone(active),
      keywords: [
        ...active.keywords,
        { id: `kw_${Date.now()}`, term: t, matchType: "phrase", priority: 3, weight: 10, hits7d: 0 },
      ],
    });
    setNewTerm("");
  }

  function exportCsv() {
    const rows = ["term,matchType,priority,weight,hits7d"];
    active.keywords.forEach((k) =>
      rows.push(`${k.term},${k.matchType},${k.priority},${k.weight},${k.hits7d}`),
    );
    const url = URL.createObjectURL(new Blob([rows.join("\n")], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "keywords.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  function bulkPaste() {
    const terms = pasteText.split("\n").map((t) => t.trim()).filter(Boolean);
    if (terms.length === 0) return;
    const c = clone(active);
    terms.forEach((term, i) =>
      c.keywords.push({
        id: `kw_${Date.now()}_${i}`, term, matchType: "phrase", priority: 3, weight: 10, hits7d: 0,
      }),
    );
    setDraftConfig(c);
    setPasteText("");
    setPasteOpen(false);
  }

  const pasteCount = pasteText.split("\n").filter((s) => s.trim()).length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" aria-hidden />
          <Input
            value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Search terms…" aria-label="Search keywords" className="pl-8"
          />
        </div>
        <Button variant="outline" size="sm" onClick={() => setPasteOpen(true)}>
          <ClipboardPaste className="h-3.5 w-3.5" aria-hidden /> Paste
        </Button>
        <Button variant="outline" size="sm" onClick={exportCsv}>
          <Download className="h-3.5 w-3.5" aria-hidden /> CSV
        </Button>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Term</TableHead>
            <TableHead className="w-[110px]">Match</TableHead>
            <TableHead className="w-[90px]">Priority</TableHead>
            <TableHead className="w-[80px]">Weight</TableHead>
            <TableHead className="w-[70px]">Hits 7d</TableHead>
            <TableHead className="w-[40px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {filtered.length === 0 ? (
            <TableRow>
              <TableCell colSpan={6} className="text-text-muted text-sm">
                No keywords {query ? `match “${query}”` : "yet"}.
              </TableCell>
            </TableRow>
          ) : (
            filtered.map((kw) => {
              const realIdx = active.keywords.findIndex((k) => k.id === kw.id);
              const isDupe = duplicates.has(realIdx);
              const firstIdx = firstOccurrence.get(kw.term.toLowerCase().trim());
              return (
                <TableRow key={kw.id}>
                  <TableCell>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Input
                          value={kw.term}
                          onChange={(e) => editRow(kw.id, { term: e.target.value })}
                          aria-invalid={isDupe}
                          aria-label={`Term: ${kw.term}`}
                          className={cn("h-8", isDupe && "border-risk")}
                        />
                      </TooltipTrigger>
                      {isDupe && firstIdx !== undefined && (
                        <TooltipContent>Duplicate of row {firstIdx + 1}</TooltipContent>
                      )}
                    </Tooltip>
                  </TableCell>
                  <TableCell>
                    <Select value={kw.matchType} onValueChange={(v) => editRow(kw.id, { matchType: v as MatchType })}>
                      <SelectTrigger size="sm" className="h-8 w-[100px]"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="phrase">Phrase</SelectItem>
                        <SelectItem value="broad">Broad</SelectItem>
                        <SelectItem value="exact">Exact</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Select value={String(kw.priority)} onValueChange={(v) => editRow(kw.id, { priority: Number(v) })}>
                      <SelectTrigger size="sm" className="h-8 w-[70px]"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {[1, 2, 3, 4, 5].map((n) => (
                          <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Input
                      type="number" value={kw.weight}
                      onChange={(e) => editRow(kw.id, { weight: Number(e.target.value) })}
                      className="h-8 w-[70px]" aria-label={`Weight for ${kw.term}`}
                    />
                  </TableCell>
                  <TableCell className="font-mono text-text-muted tabular-nums">{kw.hits7d}</TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" className="h-7 w-7"
                      onClick={() => deleteRow(kw.id)} aria-label={`Delete ${kw.term}`}>
                      <Trash2 className="h-3.5 w-3.5 text-risk" />
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>

      <div className="flex items-center gap-2">
        <Input
          value={newTerm} onChange={(e) => setNewTerm(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTerm(); } }}
          placeholder="Add a term…" aria-label="Add new keyword" className="flex-1"
        />
        <Button size="sm" onClick={addTerm}>
          <Plus className="h-3.5 w-3.5" aria-hidden /> Add
        </Button>
      </div>

      <Dialog open={pasteOpen} onOpenChange={setPasteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Bulk paste keywords</DialogTitle>
            <DialogDescription>
              One term per line. All become phrase-match with weight 10.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={pasteText} onChange={(e) => setPasteText(e.target.value)}
            rows={8} placeholder={"free prediction game\nsocial leaderboard\n…"}
            aria-label="Bulk paste keywords"
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPasteOpen(false)}>Cancel</Button>
            <Button onClick={bulkPaste} disabled={pasteCount === 0}>
              Import {pasteCount} {pasteCount === 1 ? "term" : "terms"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
