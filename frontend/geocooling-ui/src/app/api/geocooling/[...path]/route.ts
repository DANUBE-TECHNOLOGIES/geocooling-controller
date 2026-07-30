import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function backendBaseUrl(): string {
  const configured =
    process.env.GEOCOOLING_API_URL ??
    process.env.BACKEND_API_URL ??
    process.env.NEXT_PUBLIC_GEOCOOLING_API_URL;

  if (!configured) {
    throw new Error("GEOCOOLING_API_URL n'est pas configurée.");
  }

  return configured.replace(/\/$/, "");
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params;

    const search = request.nextUrl.search;
    const target =
      backendBaseUrl() +
      "/geocooling/" +
      path.join("/") +
      search;

    const controller = new AbortController();

    const timeout = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(target, {
        cache: "no-store",
        signal: controller.signal,
        headers: {
          Accept: "application/json",
        },
      });

      const text = await response.text();

      return new NextResponse(text, {
        status: response.status,
        headers: {
          "Content-Type": response.headers.get("Content-Type") ?? "application/json",
          "Cache-Control": "no-store",
        },
      });
    } finally {
      clearTimeout(timeout);
    }
  } catch (e) {
    return NextResponse.json(
      {
        error: e instanceof Error ? e.message : "Proxy GeoCooling indisponible",
      },
      { status: 503 }
    );
  }
}
