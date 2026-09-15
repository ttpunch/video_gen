import { errorMessage } from "./api";

/** Sequential requests, bounded network failures, and explicit cancellation. */
export async function pollUntil<T>(url: string, onData: (data: T) => boolean, signal: AbortSignal): Promise<void> {
  let failures = 0;
  while (!signal.aborted) {
    try {
      const response = await fetch(url, { signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]) });
      if (response.status >= 400 && response.status < 500) {
        throw new Error(`This job is unavailable (${response.status}). Open the library to check its status.`);
      }
      if (!response.ok) throw new Error(`Server returned ${response.status}`);
      const data: T = await response.json();
      failures = 0;
      if (onData(data)) return;
    } catch (error) {
      if (signal.aborted) return;
      if (++failures >= 5) {
        throw new Error(`Connection lost: ${errorMessage(error)} Your job may still be running. Refresh to reconnect.`);
      }
    }
    await new Promise<void>((resolve) => {
      const finish = () => { clearTimeout(timer); signal.removeEventListener("abort", finish); resolve(); };
      const timer = setTimeout(finish, Math.min(2000 * 2 ** failures, 15000));
      signal.addEventListener("abort", finish, { once: true });
    });
  }
}
