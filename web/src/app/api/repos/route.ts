import { NextRequest, NextResponse } from "next/server";

export async function GET() {
  const apiUrl = process.env.API_URL || "http://127.0.0.1:8000";
  try {
    const res = await fetch(`${apiUrl}/repos`);
    if (!res.ok) throw new Error("Failed to fetch repos");
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: "Failed to fetch repositories" }, { status: 500 });
  }
}
