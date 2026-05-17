import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const apiUrl = process.env.API_URL || "http://127.0.0.1:8000";
  const body = await req.json();

  try {
    const res = await fetch(`${apiUrl}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      return NextResponse.json({ error: "Backend error" }, { status: res.status });
    }

    // Stream the SSE response directly to the client
    return new NextResponse(res.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
      },
    });
  } catch (error) {
    return NextResponse.json({ error: "Failed to connect to backend" }, { status: 500 });
  }
}
