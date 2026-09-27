/**
 * WAFlow AI HTTP API client.
 *
 * This module is the single entry point for frontend HTTP requests.
 *
 * Features:
 * - Uses VITE_API_URL
 * - Adds JSON headers
 * - Parses the standard API response envelope
 * - Converts API failures into typed errors
 * - Keeps raw fetch logic away from feature components
 */

import { env } from "../../config/env";
import type {
  ApiErrorResponse,
  ApiSuccessResponse,
} from "./types";

/**
 * Custom API error.
 *
 * Feature code can catch this error and access the backend
 * error code and message without manually parsing responses.
 */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: unknown;

  constructor(
    message: string,
    status: number,
    code: string,
    details?: unknown,
  ) {
    super(message);

    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/**
 * Configuration for an API request.
 */
interface ApiRequestOptions extends RequestInit {
  /**
   * Query parameters to append to the request URL.
   */
  query?: Record<string, string | number | boolean | undefined>;
}

/**
 * Build the final API URL.
 *
 * Query parameters are encoded using URLSearchParams
 * so values are safely escaped.
 */
function buildUrl(
  path: string,
  query?: ApiRequestOptions["query"],
): string {
  const url = new URL(path, `${env.apiUrl}/`);

  if (query) {
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    });
  }

  return url.toString();
}

/**
 * Make a typed HTTP request to the WAFlow AI API.
 */
export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const { query, headers, ...requestInit } = options;

  const response = await fetch(buildUrl(path, query), {
    ...requestInit,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...headers,
    },
  });

  /**
   * Attempt to parse the backend response.
   *
   * If the server returns invalid JSON, we expose a clear
   * client-side error instead of allowing JSON parsing errors
   * to leak into feature code.
   */
  let payload:
    | ApiSuccessResponse<T>
    | ApiErrorResponse;

  try {
    payload = (await response.json()) as
      | ApiSuccessResponse<T>
      | ApiErrorResponse;
  } catch {
    throw new ApiError(
      "The API returned an invalid response.",
      response.status,
      "INVALID_API_RESPONSE",
    );
  }

  /**
   * HTTP-level failure.
   */
  if (!response.ok) {
    if (!payload.success) {
      throw new ApiError(
        payload.error.message,
        response.status,
        payload.error.code,
        payload.error.details,
      );
    }

    throw new ApiError(
      "The API request failed.",
      response.status,
      "API_REQUEST_FAILED",
    );
  }

  /**
   * Application-level failure.
   *
   * The HTTP status might be 2xx while the application
   * still reports success: false.
   */
  if (!payload.success) {
    throw new ApiError(
      payload.error.message,
      response.status,
      payload.error.code,
      payload.error.details,
    );
  }

  return payload.data;
}

/**
 * Convenience GET request.
 */
export function apiGet<T>(
  path: string,
  query?: ApiRequestOptions["query"],
): Promise<T> {
  return apiRequest<T>(path, {
    method: "GET",
    query,
  });
}

/**
 * Convenience POST request.
 */
export function apiPost<T>(
  path: string,
  body?: unknown,
): Promise<T> {
  return apiRequest<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}