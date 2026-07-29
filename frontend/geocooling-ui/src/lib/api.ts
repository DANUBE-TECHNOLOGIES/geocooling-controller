import type { GeoCoolingSnapshot } from "@/types/geocooling";

export async function fetchGeoCoolingSnapshot(): Promise<GeoCoolingSnapshot> {
  const baseUrl = process.env.GEOCOOLING_API_URL;
  if (!baseUrl) {
    throw new Error("GEOCOOLING_API_URL n’est pas configurée");
  }

  const response = await fetch(`${baseUrl}/geocooling/home-assistant`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`API GeoCooling indisponible (${response.status})`);
  }

  return response.json() as Promise<GeoCoolingSnapshot>;
}
