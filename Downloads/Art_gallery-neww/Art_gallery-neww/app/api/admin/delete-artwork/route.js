import { db } from "@/lib/db";

export async function DELETE(req) {
  try {
    const { admin_id, artwork_id } = await req.json();

    // Verify caller is admin
    const [adminRows] = await db.query("SELECT role FROM users WHERE user_id = ?", [admin_id]);
    if (adminRows.length === 0 || adminRows[0].role !== "admin") {
      return Response.json({ error: "Unauthorized" }, { status: 403 });
    }

    // Remove from wishlists first
    await db.query("DELETE FROM wishlist WHERE artwork_id = ?", [artwork_id]);

    // Delete the artwork
    await db.query("DELETE FROM artworks WHERE artwork_id = ?", [artwork_id]);

    return Response.json({ message: "Artwork deleted successfully" });
  } catch (err) {
    console.error("Delete Artwork Error:", err);
    return Response.json({ error: err.message }, { status: 500 });
  }
}
