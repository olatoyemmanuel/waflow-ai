import { useAppStore } from "../../stores/app-store";

/**
 * Top navigation bar.
 *
 * This will eventually contain:
 * - notifications
 * - search
 * - tenant switcher
 * - user profile
 * - account actions
 */
export function Topbar() {
  const toggleSidebar = useAppStore(
    (state) => state.toggleSidebar,
  );

  const toggleMobileMenu = useAppStore(
    (state) => state.toggleMobileMenu,
  );

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-4 sm:px-6">
      <div className="flex items-center gap-3">
        {/* Desktop sidebar toggle */}
        <button
          type="button"
          onClick={toggleSidebar}
          className="hidden rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 lg:block"
          aria-label="Toggle sidebar"
        >
          ☰
        </button>

        {/* Mobile menu button */}
        <button
          type="button"
          onClick={toggleMobileMenu}
          className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 lg:hidden"
          aria-label="Open navigation menu"
        >
          ☰
        </button>

        <div>
          <p className="text-sm font-semibold text-gray-950">
            Demo Business
          </p>

          <p className="hidden text-xs text-gray-400 sm:block">
            Business workspace
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {/* Notification placeholder */}
        <button
          type="button"
          className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900"
          aria-label="Notifications"
        >
          ♢
        </button>

        {/* User profile placeholder */}
        <button
          type="button"
          className="flex items-center gap-2 rounded-lg p-1.5 hover:bg-gray-50"
          aria-label="Open user menu"
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-900 text-xs font-semibold text-white">
            EM
          </span>

          <span className="hidden text-sm font-medium text-gray-700 md:block">
            Emmanuel
          </span>
        </button>
      </div>
    </header>
  );
}