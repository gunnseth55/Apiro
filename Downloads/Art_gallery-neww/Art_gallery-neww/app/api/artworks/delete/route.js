import { db } from "@/lib/db";

export async function DELETE(req) {
  try {
    const { artist_id, artwork_id } = await req.json();

    if (!artist_id || !artwork_id) {
      return Response.json({ error: "artist_id and artwork_id are required" }, { status: 400 });
    }

    // Verify the artwork belongs to this artist
    const [rows] = await db.query(
      "SELECT artwork_id FROM artworks WHERE artwork_id = ? AND artist_id = ?",
      [artwork_id, artist_id]
    );

    if (rows.length === 0) {
      return Response.json({ error: "Artwork not found or you don't own it" }, { status: 403 });
    }

    // Remove from wishlists first (foreign key safety)
    await db.query("DELETE FROM wishlist WHERE artwork_id = ?", [artwork_id]);

    // Delete the artwork
    await db.query("DELETE FROM artworks WHERE artwork_id = ?", [artwork_id]);

    return Response.json({ message: "Artwork deleted successfully" });
  } catch (err) {
    console.error("Delete Artwork Error:", err);
    return Response.json({ error: err.message }, { status: 500 });
  }
}
