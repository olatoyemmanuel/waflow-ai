import { create } from "zustand";

/**
 * Global client-side application state.
 *
 * This store should contain lightweight UI/application state.
 *
 * API/server data should NOT be stored here.
 * TanStack Query is responsible for server state.
 */
interface AppState {
  /**
   * Controls whether the desktop sidebar is collapsed.
   */
  sidebarCollapsed: boolean;

  /**
   * Controls whether the mobile navigation drawer is open.
   */
  mobileMenuOpen: boolean;

  /**
   * Collapse or expand the desktop sidebar.
   */
  toggleSidebar: () => void;

  /**
   * Open or close the mobile navigation menu.
   */
  toggleMobileMenu: () => void;

  /**
   * Explicitly close the mobile navigation menu.
   */
  closeMobileMenu: () => void;
}

/**
 * WAFlow AI global application store.
 */
export const useAppStore = create<AppState>((set) => ({
  sidebarCollapsed: false,

  mobileMenuOpen: false,

  toggleSidebar: () =>
    set((state) => ({
      sidebarCollapsed: !state.sidebarCollapsed,
    })),

  toggleMobileMenu: () =>
    set((state) => ({
      mobileMenuOpen: !state.mobileMenuOpen,
    })),

  closeMobileMenu: () =>
    set({
      mobileMenuOpen: false,
    }),
}));