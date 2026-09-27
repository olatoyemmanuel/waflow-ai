import { Outlet } from "react-router-dom";

import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/**
 * Main authenticated application layout.
 *
 * The layout provides the persistent shell around feature pages.
 *
 * Later, authentication guards will determine whether a user
 * is allowed to enter this part of the application.
 */
export function AppLayout() {
  return (
    <div className="flex min-h-screen bg-gray-50">
      {/* Persistent desktop navigation */}
      <Sidebar />

      {/* Main application area */}
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />

        <main className="flex-1 overflow-y-auto p-4 sm:p-6">
          <div className="mx-auto w-full max-w-7xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}