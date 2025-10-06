export async function GET() {
  return new Response(
    JSON.stringify({ ok: true, t: Date.now() }),
    { headers: { "content-type": "application/json" } },
  );
}