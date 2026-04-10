import { db } from "@/lib/db";

export async function POST(req) {
  try {
    const { artist_id, title, description, image_url, price, category_id } = await req.json();

    if (!artist_id || !title || !price || !category_id) {
      return Response.json({ error: "Missing required fields" }, { status: 400 });
    }

    const [result] = await db.query(
      "INSERT INTO artworks (artist_id, title, description, image_url, price, category_id) VALUES (?, ?, ?, ?, ?, ?)",
      [artist_id, title, description || "", image_url || "", price, category_id]
    );

    return Response.json({ 
      message: "Artwork uploaded successfully", 
      artwork_id: result.insertId 
    });

  } catch (error) {
    console.error("Upload Error:", error);
    return Response.json({ error: "Server error" }, { status: 500 });
  }
}
