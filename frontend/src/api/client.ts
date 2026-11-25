import axios, { AxiosError } from "axios";

/**
 * Shared Axios instance for all backend communication.
 *
 * The base URL is read from the Vite environment variable `VITE_API_URL`
 * and falls back to the local backend during development.
 */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
});

const GENERIC_MESSAGE = "Something went wrong. Please try again.";

/**
 * Maps an HTTP status code to a human-readable, user-safe message.
 * Never surfaces raw server tracebacks or internal error details.
 */
function messageForStatus(status: number | undefined): string {
  switch (status) {
    case 503:
      return "The AI service is currently unavailable. Please try again later.";
    case 504:
      return "The AI service timed out. Please try again.";
    case 422:
      return "Invalid input. Please check your entries and try again.";
    case 404:
      return "The requested resource was not found.";
    case 500:
      return "An unexpected error occurred. Please try again.";
    default:
      return GENERIC_MESSAGE;
  }
}

/**
 * Augmented Axios error carrying a user-friendly message.
 */
export interface FriendlyAxiosError extends AxiosError {
  friendlyMessage: string;
}

// Response interceptor: attach a `.friendlyMessage` to every rejected request
// so hooks/components can display safe, consistent error text.
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    let friendlyMessage: string;

    if (error.response) {
      friendlyMessage = messageForStatus(error.response.status);
    } else if (error.request) {
      friendlyMessage = "Cannot reach the server. Is the backend running?";
    } else {
      friendlyMessage = GENERIC_MESSAGE;
    }

    (error as FriendlyAxiosError).friendlyMessage = friendlyMessage;
    return Promise.reject(error);
  },
);

/**
 * Extracts a user-friendly message from an unknown error value.
 * Falls back to a generic message and never exposes raw tracebacks.
 */
export function getErrorMessage(error: unknown): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "friendlyMessage" in error &&
    typeof (error as { friendlyMessage: unknown }).friendlyMessage === "string"
  ) {
    return (error as FriendlyAxiosError).friendlyMessage;
  }
  return GENERIC_MESSAGE;
}
