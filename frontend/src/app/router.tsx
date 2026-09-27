import {
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import { AppLayout } from "../components/layout/AppLayout";
import { DashboardPage } from "../features/dashboard/pages/DashboardPage";

/**
 * Application route configuration.
 *
 * React Router 7 continues to support the declarative Routes/Route
 * approach, which is appropriate for our current application shell.
 *
 * More advanced data routers can be introduced later if the product
 * requires route loaders/actions.
 */
export function AppRouter() {
  return (
    <Routes>
      {/* Main application shell */}
      <Route element={<AppLayout />}>
        {/* Redirect the root URL to the dashboard */}
        <Route
          path="/"
          element={<Navigate to="/dashboard" replace />}
        />

        {/* Dashboard */}
        <Route
          path="/dashboard"
          element={<DashboardPage />}
        />

        {/* Placeholder routes will be implemented in later milestones */}
        <Route
          path="/inbox"
          element={<PlaceholderPage title="Inbox" />}
        />

        <Route
          path="/customers"
          element={<PlaceholderPage title="Customers" />}
        />

        <Route
          path="/whatsapp"
          element={<PlaceholderPage title="WhatsApp" />}
        />

        <Route
          path="/ai"
          element={<PlaceholderPage title="AI Assistant" />}
        />

        <Route
          path="/knowledge-base"
          element={<PlaceholderPage title="Knowledge Base" />}
        />

        <Route
          path="/automations"
          element={<PlaceholderPage title="Automations" />}
        />

        <Route
          path="/appointments"
          element={<PlaceholderPage title="Appointments" />}
        />

        <Route
          path="/campaigns"
          element={<PlaceholderPage title="Campaigns" />}
        />

        <Route
          path="/analytics"
          element={<PlaceholderPage title="Analytics" />}
        />

        <Route
          path="/billing"
          element={<PlaceholderPage title="Billing" />}
        />

        <Route
          path="/team"
          element={<PlaceholderPage title="Team" />}
        />

        <Route
          path="/settings"
          element={<PlaceholderPage title="Settings" />}
        />
      </Route>

      {/* Unknown URLs return to the dashboard. */}
      <Route
        path="*"
        element={<Navigate to="/dashboard" replace />}
      />
    </Routes>
  );
}

/**
 * Temporary page used until each feature receives
 * its own implementation.
 */
function PlaceholderPage({ title }: { title: string }) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
      <h1 className="text-xl font-bold text-gray-950">
        {title}
      </h1>

      <p className="mt-2 text-sm text-gray-500">
        This feature will be implemented in a later milestone.
      </p>
    </section>
  );
}