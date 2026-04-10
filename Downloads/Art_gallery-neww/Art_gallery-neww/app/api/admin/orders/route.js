import { db } from "@/lib/db";

export async function GET() {
  try {
    const [orders] = await db.query(
      `SELECT 
        o.order_id,
        o.buyer_name,
        o.shipping_address,
        o.ordered_at,
        a.artwork_id,
        a.title AS artwork_title,
        a.price,
        a.image_url,
        art.name AS artist_name
      FROM orders o
      JOIN artworks a ON o.artwork_id = a.artwork_id
      LEFT JOIN artists art ON a.artist_id = art.artist_id
      ORDER BY o.ordered_at DESC`
    );

    return Response.json(orders);
  } catch (err) {
    return Response.json({ error: err.message }, { status: 500 });
  }
}
