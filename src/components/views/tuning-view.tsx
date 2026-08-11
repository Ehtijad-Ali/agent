"use client";

import * as React from "react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { SectionKeywords } from "@/components/tuning/section-keywords";
import { SectionNegativeKeywords } from "@/components/tuning/section-negative-keywords";
import { SectionCountries } from "@/components/tuning/section-countries";
import { SectionScoring } from "@/components/tuning/section-scoring";
import { SectionVoice } from "@/components/tuning/section-voice";
import { SectionPresets } from "@/components/tuning/section-presets";
import { PreviewPanel } from "@/components/tuning/preview-panel";
import { UnsavedBar } from "@/components/tuning/unsaved-bar";

function SectionHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  return (
    <div className="flex flex-col">
      <span>{title}</span>
      <span className="text-[12px] text-text-muted font-normal no-underline">
        {subtitle}
      </span>
    </div>
  );
}

/**
 * TuningView — two-pane layout. Left: accordion of 6 config sections
 * (keywords / negatives / countries / scoring / voice / presets). Right:
 * sticky Live preview panel that re-scores 8 sample conversations on
 * every draft change. A sticky UnsavedBar sits at the bottom of the left
 * pane when there are unsaved changes.
 */
export function TuningView() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4 lg:gap-6 items-start">
      <div className="space-y-4 min-w-0">
        <div className="rounded-xl border bg-surface shadow-sm-signal overflow-hidden">
          <Accordion
            type="multiple"
            defaultValue={["keywords"]}
            className="px-4"
          >
            <AccordionItem value="keywords">
              <AccordionTrigger>
                <SectionHeader
                  title="Keywords"
                  subtitle="Boost scores when these terms appear"
                />
              </AccordionTrigger>
              <AccordionContent>
                <SectionKeywords />
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="negatives">
              <AccordionTrigger>
                <SectionHeader
                  title="Negative keywords"
                  subtitle="Penalise or block messages containing these terms"
                />
              </AccordionTrigger>
              <AccordionContent>
                <SectionNegativeKeywords />
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="countries">
              <AccordionTrigger>
                <SectionHeader
                  title="Countries & language"
                  subtitle="Prioritise regions and set the reply language"
                />
              </AccordionTrigger>
              <AccordionContent>
                <SectionCountries />
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="scoring">
              <AccordionTrigger>
                <SectionHeader
                  title="Scoring"
                  subtitle="Tune boosts, penalties, and intent thresholds"
                />
              </AccordionTrigger>
              <AccordionContent>
                <SectionScoring />
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="voice">
              <AccordionTrigger>
                <SectionHeader
                  title="Reply voice"
                  subtitle="Control tone, length, and language of replies"
                />
              </AccordionTrigger>
              <AccordionContent>
                <SectionVoice />
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="presets">
              <AccordionTrigger>
                <SectionHeader
                  title="Presets"
                  subtitle="Save, compare, and roll back to previous configs"
                />
              </AccordionTrigger>
              <AccordionContent>
                <SectionPresets />
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </div>

        <UnsavedBar />
      </div>

      <PreviewPanel />
    </div>
  );
}
