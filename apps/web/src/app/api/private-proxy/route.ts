import { GoogleAuth } from "google-auth-library";

export async function GET() {
  const target = process.env.PRIVATE_API_URL!;
  const auth = new GoogleAuth();
  const client = await auth.getIdTokenClient(target);
  const { data } = await client.request({ url: `${target}/ping` });
  return Response.json(data);
}