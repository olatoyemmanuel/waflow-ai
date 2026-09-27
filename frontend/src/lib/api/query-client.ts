/**
 * WAFlow AI - TanStack Query Client
 *
 * TanStack Query is responsible for managing server state.
 *
 * It handles:
 * - API request caching
 * - Loading states
 * - Error states
 * - Request retries
 * - Background refetching
 * - Cache invalidation
 *
 * Zustand will be used separately for client/UI state.
 */

import { QueryClient } from "@tanstack/react-query";

/**
 * Global QueryClient instance.
 *
 * A single QueryClient is shared across the application so that
 * different pages and components can use the same server-state cache.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      /**
       * Data is considered fresh for 30 seconds.
       *
       * This prevents unnecessary API requests when components
       * are mounted repeatedly within a short period.
       */
      staleTime: 30_000,

      /**
       * Retry failed queries twice before exposing the error
       * to the application.
       */
      retry: 2,

      /**
       * Refetch stale data when the browser window becomes active.
       *
       * This helps keep the dashboard and other server-driven
       * screens reasonably up to date.
       */
      refetchOnWindowFocus: true,
    },
  },
});