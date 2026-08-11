"use client";

import * as React from "react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useSignalStore } from "@/stores/signal-store";
import { NAV_ITEMS } from "@/lib/constants";
import {
  Inbox,
  Layers,
  BarChart3,
  FlaskConical,
  SlidersHorizontal,
  ShieldCheck,
  History,
  Search,
  Radar,
  Moon,
  Sun,
  Play,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useToast } from "@/hooks/use-toast";

const ICONS = {
  inbox: Inbox,
  triage: Layers,
  insights: BarChart3,
  playground: FlaskConical,
  tuning: SlidersHorizontal,
  safety: ShieldCheck,
  activity: History,
} as const;

/**
 * ⌘K command palette — jump to any view, run a scan, search
 * conversations, toggle theme, open triage mode.
 */
export function CommandPalette() {
  const [open, setOpen] = React.useState(false);
  const setCurrentView = useSignalStore((s) => s.setCurrentView);
  const conversations = useSignalStore((s) => s.conversations);
  const setSelectedConversationId = useSignalStore(
    (s) => s.setSelectedConversationId,
  );
  const { theme, setTheme } = useTheme();
  const { toast } = useToast();

  // Open via ⌘K (handled by TopBar) or via the open event
  React.useEffect(() => {
    function onOpen() {
      setOpen(true);
    }
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("signal:open-palette", onOpen);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("signal:open-palette", onOpen);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  function go(view: (typeof NAV_ITEMS)[number]["id"]) {
    setCurrentView(view);
    setOpen(false);
  }

  function runScan() {
    setOpen(false);
    toast({
      title: "Scan started",
      description: "Listening across Discord, Telegram, Facebook, and Reddit.",
    });
  }

  function toggleTheme() {
    setTheme(theme === "dark" ? "light" : "dark");
    setOpen(false);
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Type a command or search…" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>

        <CommandGroup heading="Navigate">
          {NAV_ITEMS.map((item) => {
            const Icon = ICONS[item.id];
            return (
              <CommandItem
                key={item.id}
                value={`${item.label} ${item.shortcut}`}
                onSelect={() => go(item.id)}
              >
                <Icon className="h-4 w-4 mr-2 text-text-muted" />
                <span>{item.label}</span>
                <kbd className="ml-auto text-[10px] font-mono text-text-muted">
                  {item.shortcut}
                </kbd>
              </CommandItem>
            );
          })}
        </CommandGroup>

        <CommandGroup heading="Actions">
          <CommandItem value="run scan" onSelect={runScan}>
            <Play className="h-4 w-4 mr-2 text-text-muted" />
            <span>Run scan</span>
          </CommandItem>
          <CommandItem value="toggle theme dark light" onSelect={toggleTheme}>
            {theme === "dark" ? (
              <Sun className="h-4 w-4 mr-2 text-text-muted" />
            ) : (
              <Moon className="h-4 w-4 mr-2 text-text-muted" />
            )}
            <span>Toggle theme</span>
          </CommandItem>
        </CommandGroup>

        <CommandGroup heading="Conversations">
          {conversations.slice(0, 8).map((c) => (
            <CommandItem
              key={c.id}
              value={`${c.message} ${c.community} ${c.authorPseudonym}`}
              onSelect={() => {
                setSelectedConversationId(c.id);
                setCurrentView("inbox");
                setOpen(false);
              }}
            >
              <Search className="h-4 w-4 mr-2 text-text-muted" />
              <span className="truncate">{c.message.slice(0, 60)}</span>
              <span className="ml-auto text-[10px] font-mono text-text-muted">
                {c.score}
              </span>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
