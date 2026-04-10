import { db } from "@/lib/db";
import bcrypt from "bcryptjs";

export async function POST(req) {
  try {
    const { email, password } = await req.json();

    if (!email || !password) {
      return Response.json({ error: "Email and password are required" }, { status: 400 });
    }

    // Find the user and their associated artist profile
    const [rows] = await db.query(
      `SELECT u.user_id, u.email, u.password_hash, a.artist_id, a.name, a.slug 
       FROM users u 
       JOIN artists a ON u.user_id = a.user_id 
       WHERE u.email = ? AND u.role = 'artist'`,
      [email]
    );

    if (rows.length === 0) {
      return Response.json({ error: "No artist found with this email" }, { status: 404 });
    }

    const artistData = rows[0];

    // Verify password
    const isMatch = await bcrypt.compare(password, artistData.password_hash);
    if (!isMatch) {
      return Response.json({ error: "Incorrect password" }, { status: 401 });
    }

    return Response.json({ 
      message: "Login successful", 
      artist_id: artistData.artist_id,
      name: artistData.name,
      slug: artistData.slug
    });

  } catch (error) {
    console.error("Login Error:", error);
    return Response.json({ error: "Server error" }, { status: 500 });
  }
}
