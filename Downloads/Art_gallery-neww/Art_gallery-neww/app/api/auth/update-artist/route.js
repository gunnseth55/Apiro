import { db } from "@/lib/db";

export async function PUT(req) {
  try {
    const { artist_id, name, biography, country, profile_image } = await req.json();

    if (!artist_id) {
      return Response.json({ error: "artist_id is required" }, { status: 400 });
    }

    // Build dynamic update fields
    const fields = [];
    const values = [];

    if (name !== undefined && name.trim()) { fields.push("name = ?"); values.push(name.trim()); }
    if (biography !== undefined) { fields.push("biography = ?"); values.push(biography); }
    if (country !== undefined && country.trim()) { fields.push("country = ?"); values.push(country.trim()); }
    if (profile_image !== undefined && profile_image.trim()) { fields.push("profile_image = ?"); values.push(profile_image.trim()); }

    if (fields.length === 0) {
      return Response.json({ error: "No fields to update" }, { status: 400 });
    }

    values.push(artist_id);

    await db.query(
      `UPDATE artists SET ${fields.join(", ")} WHERE artist_id = ?`,
      values
    );

    // If name changed, also update users table and regenerate slug
    if (name !== undefined && name.trim()) {
      const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)+/g, "");
      const [artistRow] = await db.query("SELECT user_id FROM artists WHERE artist_id = ?", [artist_id]);
      if (artistRow.length > 0) {
        await db.query("UPDATE users SET name = ? WHERE user_id = ?", [name.trim(), artistRow[0].user_id]);
        await db.query("UPDATE artists SET slug = ? WHERE artist_id = ?", [slug, artist_id]);
      }
    }

    return Response.json({ message: "Profile updated successfully" });
  } catch (error) {
    console.error("Update Error:", error);
    return Response.json({ error: "Server error" }, { status: 500 });
  }
}
