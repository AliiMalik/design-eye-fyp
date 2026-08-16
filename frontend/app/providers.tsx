"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";
import { ThemeProvider } from "next-themes";
import { useState } from "react";
import { Toaster } from "sonner";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );

  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="light"
      enableSystem
      disableTransitionOnChange
    >
      {/*
        reducedMotion="user" drops transform and layout animation for users who
        ask for it, while still resolving opacity to its target. Components must
        therefore never branch their rendered STRUCTURE on useReducedMotion():
        that value differs between server and client, and the resulting
        hydration mismatch strands revealed content at opacity 0.
      */}
      <MotionConfig reducedMotion="user">
        <QueryClientProvider client={client}>
          {children}
          <Toaster
            position="bottom-right"
            toastOptions={{
              classNames: {
                toast:
                  "!bg-[var(--color-surface)] !text-[var(--color-ink)] !border-[var(--color-hairline)] !rounded-2xl",
              },
            }}
          />
        </QueryClientProvider>
      </MotionConfig>
    </ThemeProvider>
  );
}
