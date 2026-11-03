import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function backendBase() {
  const base = process.env.BOT_API_URL?.replace(/\/$/, "");
  if (!base) {
    throw new Error("BOT_API_URL is not set");
  }
  return base;
}

async function proxy(req: NextRequest, path: string[]) {
  try {
    const target = `${backendBase()}/api/${path.join("/")}${req.nextUrl.search}`;
    const init: RequestInit = {
      method: req.method,
      headers: {
        "Content-Type": "application/json",
      },
      cache: "no-store",
    };
    if (req.method !== "GET" && req.method !== "HEAD") {
      init.body = await req.text();
    }
    const upstream = await fetch(target, init);
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") || "application/json",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Proxy failed";
    return NextResponse.json({ ok: false, message }, { status: 502 });
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}

export async function POST(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}
