import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function backendBaseUrl(): string {
  const configured = process.env.GEOCOOLING_API_URL
    ?? process.env.BACKEND_API_URL
    ?? process.env.NEXT_PUBLIC_GEOCOOLING_API_URL;

  if (!configured) {
    throw new Error(
      "GEOCOOLING_API_URL n’est pas configurée dans l’environnement du frontend",
    );
  }

  return configured.replace(/\/$/, "");
}

export async function GET() {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(`${backendBaseUrl()}/geocooling/home-assistant`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });

      const text = await response.text();
      if (!response.ok) {
        return NextResponse.json(
          { error: `Backend GeoCooling indisponible (${response.status})` },
          { status: 502 },
        );
      }

      let payload: unknown;
      try {
        payload = JSON.parse(text);
      } catch {
        return NextResponse.json(
          { error: "Le backend GeoCooling a retourné une réponse non JSON" },
          { status: 502 },
        );
      }

      return NextResponse.json(payload, {
        status: 200,
        headers: { "Cache-Control": "no-store, max-age=0" },
      });
    } finally {
      clearTimeout(timeout);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "Erreur de connexion GeoCooling";
    const status = error instanceof Error && error.name === "AbortError" ? 504 : 503;
    return NextResponse.json({ error: message }, { status });
  }
}
