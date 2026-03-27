import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  const { description } = await request.json();
  const orchestratorUrl = process.env.NEXT_PUBLIC_ORCHESTRATOR_URL || 'http://localhost:3000';
  try {
    const res = await fetch(`${orchestratorUrl}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description }),
    });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: 'Orchestrator unavailable' }, { status: 500 });
  }
}
