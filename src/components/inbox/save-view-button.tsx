"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Check, Save } from "lucide-react";

/** "Save this view" trigger + naming dialog. Stores in local state only. */
export function SaveViewButton({
  onSave,
}: {
  onSave: (name: string) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");

  return (
    <div className="p-3 border-t">
      <Button
        variant="outline"
        size="sm"
        className="w-full"
        onClick={() => {
          setName("");
          setOpen(true);
        }}
      >
        <Save className="h-3.5 w-3.5" />
        Save this view
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Save current view</DialogTitle>
            <DialogDescription>
              Name this filter combination so you can return to it later. It
              stays available while this session is open.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="view-name">View name</Label>
            <Input
              id="view-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Discord high intent — last week"
              autoFocus
            />
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="ghost">Cancel</Button>
            </DialogClose>
            <Button
              disabled={!name.trim()}
              onClick={() => {
                onSave(name.trim());
                setOpen(false);
              }}
            >
              <Check className="h-3.5 w-3.5" />
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
