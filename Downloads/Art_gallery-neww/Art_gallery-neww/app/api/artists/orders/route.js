import { db } from "@/lib/db";

export async function GET(req) {
  try {
    const { searchParams } = new URL(req.url);
    const artist_id = searchParams.get("artist_id");

    if (!artist_id) {
      return Response.json({ error: "artist_id is required" }, { status: 400 });
    }

    // Fetch orders for artworks belonging to this artist
    const [orders] = await db.query(
      `SELECT 
        o.order_id,
        o.buyer_name,
        o.shipping_address,
        o.ordered_at,
        a.artwork_id,
        a.title AS artwork_title,
        a.price,
        a.image_url
      FROM orders o
      JOIN artworks a ON o.artwork_id = a.artwork_id
      WHERE a.artist_id = ?
      ORDER BY o.ordered_at DESC`,
      [artist_id]
    );

    return Response.json(orders);
  } catch (err) {
    // If orders table doesn't exist yet, return empty array
    if (err.message.includes("doesn't exist")) {
      return Response.json([]);
    }
    return Response.json({ error: err.message }, { status: 500 });
  }
}
