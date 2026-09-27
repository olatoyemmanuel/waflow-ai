/**
 * Dashboard page.
 *
 * This is intentionally a presentation-only shell at this stage.
 *
 * Real dashboard metrics will later come from the FastAPI backend
 * through TanStack Query.
 */
export function DashboardPage() {
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

      <p className="mt-2 text-2xl font-bold text-gray-950">{value}</p>

      <p className="mt-1 text-xs text-gray-400">{description}</p>
    </div>
  );
}