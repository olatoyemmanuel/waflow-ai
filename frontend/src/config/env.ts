/**
 * WAFlow AI frontend environment configuration.
 *
 * This file provides one controlled location for reading
 * frontend environment variables.
 *
 * Vite exposes variables prefixed with VITE_ through import.meta.env.
 */

const apiUrl = import.meta.env.VITE_API_URL;

/**
 * Fail early when the API URL has not been configured.
 *
 * This prevents the application from silently making requests
 * to an undefined or incorrect backend URL.
 */
if (!apiUrl) {
  throw new Error(
    "VITE_API_URL is not configured. Please check frontend/.env.",
  );
}

/**
 * Application environment configuration.
 */
export const env = {
  apiUrl,
} as const;
