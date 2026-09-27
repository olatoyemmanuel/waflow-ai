/**
 * WAFlow AI API response types.
 *
 * The backend follows a consistent response envelope:
 *
 * {
 *   success: true,
 *   data: {},
 *   meta: {}
 * }
 *
 * Keeping these types centralized prevents every feature from
 * inventing its own API response structure.
 */

/**
 * Successful API response.
 *
 * T represents the actual payload returned by the endpoint.
 */
export interface ApiSuccessResponse<T> {
  success: true;
  data: T;
  meta?: Record<string, unknown>;
}

/**
 * API error payload.
 */
export interface ApiErrorResponse {
  success: false;
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

/**
 * Health endpoint payload.
 */
export interface HealthResponse {
  status: "healthy";
}

/**
 * Generic API response envelope.
 */
export type ApiResponse<T> =
  | ApiSuccessResponse<T>
  | ApiErrorResponse;