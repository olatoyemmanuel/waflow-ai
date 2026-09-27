import { NavLink } from "react-router-dom";

import { useAppStore } from "../../stores/app-store";

/**
 * Main WAFlow AI navigation items.
 *
 * Business functionality will be implemented in later milestones.
 * For now, these routes provide the application's navigation structure.
 */
const navigationItems = [
  {
    label: "Dashboard",
    path: "/dashboard",
    icon: "⌂",
  },
  {
    label: "Inbox",
    path: "/inbox",
    icon: "✉",
  },
  {
    label: "Customers",
    path: "/customers",
    icon: "♙",
  },
  {
    label: "WhatsApp",
    path: "/whatsapp",
    icon: "◉",
  },
  {
    label: "AI Assistant",
    path: "/ai",
    icon: "✦",
  },
  {
    label: "Knowledge Base",
    path: "/knowledge-base",
    icon: "▤",
  },
  {
    label: "Automations",
    path: "/automations",
    icon: "⚙",
  },
  {
    label: "Appointments",
    path: "/appointments",
    icon: "□",
  },
  {
    label: "Campaigns",
    path: "/campaigns",
    icon: "➤",
  },
  {
    label: "Analytics",
    path: "/analytics",
    icon: "▥",
  },
];

/**
 * Secondary navigation items.
 */
const secondaryItems = [
  {
    label: "Billing",
    path: "/billing",
    icon: "₦",
  },
  {
    label: "Team",
    path: "/team",
    icon: "♟",
  },
  {
    label: "Settings",
    path: "/settings",
    icon: "⚙",
  },
];

/**
 * WAFlow AI sidebar.
 */
export function Sidebar() {
  const sidebarCollapsed = useAppStore(
    (state) => state.sidebarCollapsed,
  );

  return (
    <aside
      className={[
        "hidden h-screen shrink-0 border-r border-gray-200 bg-white transition-all duration-200 lg:flex lg:flex-col",
        sidebarCollapsed ? "w-20" : "w-64",
      ].join(" ")}
    >
      {/* Brand */}
      <div className="flex h-16 items-center border-b border-gray-200 px-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-sm font-bold text-white">
          W
        </div>

        {!sidebarCollapsed && (
          <div className="ml-3">
            <p className="text-sm font-bold text-gray-950">
              WAFlow AI
            </p>

            <p className="text-xs text-gray-400">
              WhatsApp automation
            </p>
          </div>
        )}
      </div>

      {/* Primary navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {navigationItems.map((item) => (
          <SidebarLink
            key={item.path}
            label={item.label}
            path={item.path}
            icon={item.icon}
            collapsed={sidebarCollapsed}
          />
        ))}

        <div className="my-4 border-t border-gray-100" />

        {secondaryItems.map((item) => (
          <SidebarLink
            key={item.path}
            label={item.label}
            path={item.path}
            icon={item.icon}
            collapsed={sidebarCollapsed}
          />
        ))}
      </nav>

      {/* Workspace information */}
      <div className="border-t border-gray-200 p-3">
        <div className="rounded-lg bg-gray-50 p-3">
          {!sidebarCollapsed ? (
            <>
              <p className="text-xs font-medium text-gray-400">
                WORKSPACE
              </p>

              <p className="mt-1 truncate text-sm font-semibold text-gray-800">
                Demo Business
              </p>
            </>
          ) : (
            <div className="text-center text-xs font-bold text-gray-500">
              DB
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

interface SidebarLinkProps {
  label: string;
  path: string;
  icon: string;
  collapsed: boolean;
}

/**
 * Reusable sidebar navigation link.
 */
function SidebarLink({
  label,
  path,
  icon,
  collapsed,
}: SidebarLinkProps) {
  return (
    <NavLink
      to={path}
      className={({ isActive }) =>
        [
          "flex items-center rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
          isActive
            ? "bg-emerald-50 text-emerald-700"
            : "text-gray-600 hover:bg-gray-50 hover:text-gray-950",
          collapsed ? "justify-center" : "gap-3",
        ].join(" ")
      }
      title={collapsed ? label : undefined}
    >
      <span className="flex h-5 w-5 shrink-0 items-center justify-center text-base">
        {icon}
      </span>

      {!collapsed && <span>{label}</span>}
    </NavLink>
  );
}