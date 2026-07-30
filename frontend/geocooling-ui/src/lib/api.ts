import type { GeoCoolingSnapshot } from "@/types/geocooling";

const API = process.env.GEOCOOLING_API_URL;

async function request<T>(
  endpoint: string,
  signal?: AbortSignal
): Promise<T> {

  if (!API) {
    throw new Error("GEOCOOLING_API_URL n'est pas configurée");
  }

  const response = await fetch(`${API}${endpoint}`, {
    cache: "no-store",
    signal,
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json() as Promise<T>;
}

export function fetchGeoCoolingSnapshot(
  signal?: AbortSignal
): Promise<GeoCoolingSnapshot> {
  return request(
    "/geocooling/home-assistant",
    signal
  );
}
