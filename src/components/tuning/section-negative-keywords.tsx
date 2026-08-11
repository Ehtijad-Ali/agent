"use client";

import * as React from "react";
import { useSignalStore } from "@/stores/signal-store";
import type { MatchType, NegativeKeywordRule, TuningConfig } from "@/lib/types";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Plus, Trash2, ClipboardPaste, Download, Search } from "lucide-react";
import { cn } from "@/lib/utils";

function clone(c: TuningConfig): TuningConfig {
  return JSON.parse(JSON.stringify(c));
}

/**
 * SectionNegativeKeywords — same table UI as SectionKeywords but with
 * rose-tinted accents and negative-only weights. Section container has
 * `border-risk/30` per spec.
 */
export function SectionNegativeKeywords() {
  const config = useSignalStore((s) => s.config);
  const draftConfig = useSignalStore((s) => s.draftConfig);
  const setDraftConfig = useSignalStore((s) => s.setDraftConfig);
  const active = draftConfig ?? config;

  const [query, setQuery] = React.useState("");
  const [newTerm, setNewTerm] = React.useState("");
  const [pasteOpen, setPasteOpen] = React.useState(false);
  const [pasteText, setPasteText] = React.useState("");

  const filtered = React.useMemo(() => {
    if (!query.trim()) return active.negativeKeywords;
    const q = query.toLowerCase();
    return active.negativeKeywords.filter((k) =>
      k.term.toLowerCase().includes(q),
    );
  }, [active.negativeKeywords, query]);

  function editRow(id: string, patch: Partial<NegativeKeywordRule>) {
    setDraftConfig({
      ...clone(active),
      negativeKeywords: active.negativeKeywords.map((k) =>
        k.id === id ? { ...k, ...patch } : k,
      ),
    });
  }

  function deleteRow(id: string) {
    setDraftConfig({
      ...clone(active),
      negativeKeywords: active.negativeKeywords.filter((k) => k.id !== id),
    });
  }

  function addTerm() {
    const t = newTerm.trim();
    if (!t) return;
    const nk: NegativeKeywordRule = {
      id: `nk_${Date.now()}`,
      term: t,
      matchType: "phrase",
      weight: -15,
      hits7d: 0,
    };
    setDraftConfig({
      ...clone(active),
      negativeKeywords: [...active.negativeKeywords, nk],
    });
    setNewTerm("");
  }

  function exportCsv() {
    const rows = ["term,matchType,weight,hits7d"];
    active.negativeKeywords.forEach((k) =>
      rows.push(`${k.term},${k.matchType},${k.weight},${k.hits7d}`),
    );
    const blob = new Blob([rows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "negative-keywords.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  function bulkPaste() {
    const terms = pasteText
      .split("\n")
      .map((t) => t.trim())
      .filter(Boolean);
    if (terms.length === 0) return;
    const c = clone(active);
    terms.forEach((term, i) =>
      c.negativeKeywords.push({
        id: `nk_${Date.now()}_${i}`,
        term,
        matchType: "phrase",
        weight: -15,
        hits7d: 0,
      }),
    );
    setDraftConfig(c);
    setPasteText("");
    setPasteOpen(false);
  }

  const pasteCount = pasteText.split("\n").filter((s) => s.trim()).length;

  return (
    <div
      className={cn(
        "space-y-3 -mx-2 px-2 py-2 rounded-md border border-risk/30 bg-risk/5",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[180px]">
          <Search
            className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted"
            aria-hidden
          />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search negative terms…"
            aria-label="Search negative keywords"
            className="pl-8"
          />
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setPasteOpen(true)}
        >
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
            <TableHead className="w-[90px]">Weight</TableHead>
            <TableHead className="w-[70px]">Hits 7d</TableHead>
            <TableHead className="w-[40px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {filtered.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="text-text-muted text-sm">
                No negative keywords {query ? `match “${query}”` : "yet"}.
              </TableCell>
            </TableRow>
          ) : (
            filtered.map((nk) => (
              <TableRow key={nk.id}>
                <TableCell>
                  <Input
                    value={nk.term}
                    onChange={(e) => editRow(nk.id, { term: e.target.value })}
                    aria-label={`Term: ${nk.term}`}
                    className="h-8"
                  />
                </TableCell>
                <TableCell>
                  <Select
                    value={nk.matchType}
                    onValueChange={(v) =>
                      editRow(nk.id, { matchType: v as MatchType })
                    }
                  >
                    <SelectTrigger size="sm" className="h-8 w-[100px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="phrase">Phrase</SelectItem>
                      <SelectItem value="broad">Broad</SelectItem>
                      <SelectItem value="exact">Exact</SelectItem>
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell>
                  <Input
                    type="number"
                    value={nk.weight}
                    onChange={(e) =>
                      editRow(nk.id, { weight: Number(e.target.value) })
                    }
                    className="h-8 w-[80px] text-risk"
                    aria-label={`Weight for ${nk.term}`}
                  />
                </TableCell>
                <TableCell className="font-mono text-text-muted tabular-nums">
                  {nk.hits7d}
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => deleteRow(nk.id)}
                    aria-label={`Delete ${nk.term}`}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-risk" />
                  </Button>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      <div className="flex items-center gap-2">
        <Input
          value={newTerm}
          onChange={(e) => setNewTerm(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addTerm();
            }
          }}
          placeholder="Add a negative term…"
          aria-label="Add new negative keyword"
          className="flex-1"
        />
        <Button size="sm" variant="outline" onClick={addTerm}>
          <Plus className="h-3.5 w-3.5" aria-hidden /> Add
        </Button>
      </div>

      <Dialog open={pasteOpen} onOpenChange={setPasteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Bulk paste negative keywords</DialogTitle>
            <DialogDescription>
              One term per line. All become phrase-match with weight -15.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            rows={8}
            placeholder={"real money\ndeposit required\n…"}
            aria-label="Bulk paste negative keywords"
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPasteOpen(false)}>
              Cancel
            </Button>
            <Button onClick={bulkPaste} disabled={pasteCount === 0}>
              Import {pasteCount} {pasteCount === 1 ? "term" : "terms"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
