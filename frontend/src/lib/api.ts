export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
