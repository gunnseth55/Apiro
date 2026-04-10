import { db } from "@/lib/db";

export async function DELETE(req) {
  try {
    const { admin_id, user_id } = await req.json();

    // Verify caller is admin
    const [adminRows] = await db.query("SELECT role FROM users WHERE user_id = ?", [admin_id]);
    if (adminRows.length === 0 || adminRows[0].role !== "admin") {
      return Response.json({ error: "Unauthorized" }, { status: 403 });
    }

    // Prevent admin from deleting themselves
    if (parseInt(admin_id) === parseInt(user_id)) {
      return Response.json({ error: "Cannot delete your own admin account." }, { status: 400 });
    }

    // Delete dependent records first (wishlist, artist_reviews, donations)
    await db.query("DELETE FROM wishlist WHERE user_id = ?", [user_id]);
    await db.query("DELETE FROM artist_reviews WHERE user_id = ?", [user_id]);
    await db.query("DELETE FROM donations WHERE user_id = ?", [user_id]);

    // If they are an artist, delete their artworks and artist profile too
    const [artistRows] = await db.query("SELECT artist_id FROM artists WHERE user_id = ?", [user_id]);
    for (const artist of artistRows) {
      await db.query("DELETE FROM artist_reviews WHERE artist_id = ?", [artist.artist_id]);
      await db.query("DELETE FROM donations WHERE artist_id = ?", [artist.artist_id]);
      await db.query("DELETE FROM artworks WHERE artist_id = ?", [artist.artist_id]);
      await db.query("DELETE FROM artists WHERE artist_id = ?", [artist.artist_id]);
    }

    await db.query("DELETE FROM users WHERE user_id = ?", [user_id]);

    return Response.json({ message: "User deleted successfully" });
  } catch (err) {
    console.error("Delete User Error:", err);
    return Response.json({ error: err.message }, { status: 500 });
  }
}
