"use client";

import { ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CountryFlag } from "@/components/signal/primitives";
import { PLATFORMS, COUNTRIES } from "@/lib/constants";
import { format } from "date-fns";
import type { Conversation } from "@/lib/types";

function MetaRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3 py-2 border-b border-border/60 last:border-0">
      <span className="text-xs text-text-muted font-medium uppercase tracking-wide">
        {label}
      </span>
      <span className="text-sm text-text text-right">{children}</span>
    </div>
  );
}

export function InspectorSource({ c }: { c: Conversation }) {
  const platformMeta = PLATFORMS[c.platform];
  const countryMeta = COUNTRIES.find((x) => x.code === c.country);
  const postedDate = new Date(c.postedAt);

  return (
    <div className="px-4 py-4 overflow-y-auto">
      <div className="space-y-0">
        <MetaRow label="Platform">
          <span className="font-mono">
            <span aria-hidden>{platformMeta?.glyph}</span> {c.platform}
          </span>
        </MetaRow>
        <MetaRow label="Community">
          <span className="font-mono">{c.community}</span>
        </MetaRow>
        <MetaRow label="Country">
          <span className="inline-flex items-center gap-1.5">
            <CountryFlag code={c.country} />
            <span>{countryMeta?.name ?? c.country}</span>
          </span>
        </MetaRow>
        <MetaRow label="Language">
          <Badge variant="outline" className="font-mono uppercase">
            {c.language}
          </Badge>
        </MetaRow>
        <MetaRow label="Posted">
          <span className="font-mono tabular-nums">
            {format(postedDate, "d MMM yyyy · HH:mm")}
          </span>
        </MetaRow>
        <MetaRow label="Author">
          <span className="font-mono">{c.authorPseudonym}</span>
        </MetaRow>
      </div>

      <div className="mt-4">
        {c.sourceUrl ? (
          <Button asChild variant="outline" size="sm" className="w-full">
            <a
              href={c.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Open original message in a new tab"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Open original
            </a>
          </Button>
        ) : (
          <p className="text-xs text-text-muted italic">
            Original source URL unavailable.
          </p>
        )}
      </div>
    </div>
  );
}
