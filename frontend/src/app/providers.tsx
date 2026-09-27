/**
 * WAFlow AI - Application Providers
 *
 * This file contains the providers that must be available
 * throughout the React application.
 */

import type { ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";

import { queryClient } from "../lib/api/query-client";

interface AppProvidersProps {
  /**
   * React application content that will be wrapped
   * by the global providers.
   */
  children: ReactNode;
}

/**
 * Global WAFlow AI application providers.
 *
 * TanStack Query is currently the first global provider.
 * Additional providers such as authentication, theme,
 * notifications, and other application services can be
 * added here as the platform grows.
 */
export function AppProviders({ children }: AppProvidersProps) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}