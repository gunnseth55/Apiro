import { db } from "@/lib/db";

export async function POST(req) {
  try {
    const { user_id } = await req.json();
    if (!user_id) return Response.json({ isAdmin: false });

    const [rows] = await db.query("SELECT role FROM users WHERE user_id = ?", [user_id]);
    if (rows.length === 0) return Response.json({ isAdmin: false });

    return Response.json({ isAdmin: rows[0].role === "admin" });
  } catch (err) {
    return Response.json({ isAdmin: false });
  }
}
