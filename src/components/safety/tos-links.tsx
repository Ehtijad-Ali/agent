"use client";

import * as React from "react";
import { ExternalLink } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PLATFORMS } from "@/lib/constants";
import type { Platform } from "@/lib/types";

/* ============================================================
   Platform ToS links — guardrail #9.
   For each supported platform, render the glyph + label + an
   external link to its terms-of-service URL.
   ============================================================ */

const PLATFORM_ORDER: Platform[] = [
  "discord",
  "telegram",
  "facebook",
  "reddit",
];

export function TosLinks() {
  return (
    <Card id="tos-links" className="scroll-mt-24 py-5">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">Platform terms of service</CardTitle>
        <CardDescription>
          Discovery and reply cadence respect each platform&apos;s published
          terms. Opens in a new tab.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {PLATFORM_ORDER.map((p) => {
            const meta = PLATFORMS[p];
            return (
              <li key={p}>
                <a
                  href={meta.tosUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface px-3 py-2.5 hover:bg-surface-sunk transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
                  aria-label={`${meta.label} — terms of service (opens in new tab)`}
                >
                  <span className="flex items-center gap-2.5 min-w-0">
                    <span aria-hidden className="text-base leading-none">
                      {meta.glyph}
                    </span>
                    <span className="text-sm font-medium text-text truncate">
                      {meta.label}
                    </span>
                  </span>
                  <ExternalLink
                    className="h-3.5 w-3.5 text-text-muted shrink-0"
                    aria-hidden
                  />
                </a>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
