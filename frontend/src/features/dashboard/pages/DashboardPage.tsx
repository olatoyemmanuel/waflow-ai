/**
 * WAFlow AI Dashboard.
 *
 * The dashboard currently contains presentation-level metrics
 * and the first real backend integration: API health status.
 */

import { useHealthQuery } from "../api/use-health";

/**
 * Main dashboard page.
 */
export function DashboardPage() {
  const healthQuery = useHealthQuery();

  /**
   * Determine the API connection state from the TanStack Query state.
   */
  const apiStatus = healthQuery.isLoading
    ? "Connecting"
    : healthQuery.isSuccess
      ? "Connected"
      : "Unavailable";

  const apiStatusClass =
    healthQuery.isSuccess
      ? "text-emerald-600"
      : healthQuery.isLoading
        ? "text-amber-600"
        : "text-red-600";

  return (
    <section className="space-y-6">
      {/* Page heading */}
      <div>
        <p className="text-sm font-medium text-emerald-600">
          Overview
        </p>

        <h1 className="mt-1 text-2xl font-bold tracking-tight text-gray-950">
          Dashboard
        </h1>

        <p className="mt-2 text-sm text-gray-500">
          Monitor your WhatsApp conversations, customers, AI activity,
          and business performance.
        </p>
      </div>

      {/* API connection status */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-gray-950">
              Platform connection
            </h2>

            <p className="mt-1 text-sm text-gray-500">
              Connection status between the WAFlow AI frontend and API.
            </p>
          </div>

          <div
            className={`flex items-center gap-2 text-sm font-semibold ${apiStatusClass}`}
          >
            <span
              className={[
                "h-2.5 w-2.5 rounded-full",
                healthQuery.isSuccess
                  ? "bg-emerald-500"
                  : healthQuery.isLoading
                    ? "bg-amber-500"
                    : "bg-red-500",
              ].join(" ")}
            />

            {apiStatus}
          </div>
        </div>

        {/* Display the backend health response when available. */}
        {healthQuery.isSuccess && (
          <p className="mt-4 rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            FastAPI backend is healthy and responding correctly.
          </p>
        )}

        {/* Display a user-friendly error when the API is unavailable. */}
        {healthQuery.isError && (
          <p className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            The backend API could not be reached. Make sure the FastAPI
            server is running on port 8000.
          </p>
        )}
      </div>

      {/* KPI cards */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <DashboardMetric
          label="Conversations"
          value="0"
          description="Active conversations"
        />

        <DashboardMetric
          label="Customers"
          value="0"
          description="Total customers"
        />

        <DashboardMetric
          label="AI Resolution"
          value="0%"
          description="Resolved by AI"
        />

        <DashboardMetric
          label="Response Time"
          value="—"
          description="Average response time"
        />
      </div>

      {/* Main dashboard sections */}
      <div className="grid gap-6 xl:grid-cols-3">
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm xl:col-span-2">
          <h2 className="text-base font-semibold text-gray-950">
            Conversation activity
          </h2>

          <p className="mt-2 text-sm text-gray-500">
            Conversation analytics will appear here once the backend
            analytics API is connected.
          </p>

          <div className="mt-6 flex h-56 items-center justify-center rounded-lg border border-dashed border-gray-300 bg-gray-50">
            <span className="text-sm text-gray-400">
              Analytics visualization
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-950">
            AI assistant
          </h2>

          <p className="mt-2 text-sm text-gray-500">
            AI performance and automation status will appear here.
          </p>

          <div className="mt-6 rounded-lg bg-gray-50 p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">
                Status
              </span>

              <span className="inline-flex items-center gap-2 text-sm font-medium text-amber-600">
                <span className="h-2 w-2 rounded-full bg-amber-500" />
                Not connected
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

interface DashboardMetricProps {
  label: string;
  value: string;
  description: string;
}

/**
 * Reusable dashboard KPI card.
 */
function DashboardMetric({
  label,
  value,
  description,
}: DashboardMetricProps) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-gray-500">{label}</p>

      <p className="mt-2 text-2xl font-bold text-gray-950">
        {value}
      </p>

      <p className="mt-1 text-xs text-gray-400">
        {description}
      </p>
    </div>
  );
}