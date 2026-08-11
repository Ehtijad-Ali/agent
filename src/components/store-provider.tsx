"use client";

import * as React from "react";
import { useSignalStore } from "@/stores/signal-store";

/**
 * Hydrates the Zustand store from localStorage on the client only,
 * avoiding SSR mismatch.
 */
export function SignalStoreProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const hydrate = useSignalStore((s) => s.hydrate);

  React.useEffect(() => {
    hydrate();
  }, [hydrate]);

  return <>{children}</>;
}
