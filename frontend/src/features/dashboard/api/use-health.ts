/**
 * Dashboard health query.
 *
 * TanStack Query owns the server state.
 *
 * The component does not need to know:
 * - how fetch works
 * - what URL is used
 * - how errors are parsed
 *
 * It simply consumes the query result.
 */

import { useQuery } from "@tanstack/react-query";

import { getHealth } from "../../../lib/api/health";

/**
 * Query key used by TanStack Query.
 *
 * Keeping query keys centralized helps with future
 * cache invalidation and refetching.
 */
export const healthQueryKey = ["health"] as const;

/**
 * Fetch backend health information.
 */
export function useHealthQuery() {
  return useQuery({
    queryKey: healthQueryKey,
    queryFn: getHealth,

    /**
     * Health information does not need to be fetched
     * repeatedly every few seconds by the dashboard.
     *
     * We will introduce dedicated monitoring later.
     */
    staleTime: 30_000,

    /**
     * Avoid retrying health checks indefinitely.
     */
    retry: 1,
  });
}