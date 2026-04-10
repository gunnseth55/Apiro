import { db } from "@/lib/db";

export async function GET() {
  try {
    const [userCount] = await db.query("SELECT COUNT(*) as count FROM users WHERE role IN ('user', 'admin')");
    const [artistCount] = await db.query("SELECT COUNT(*) as count FROM artists");
    const [artworkCount] = await db.query("SELECT COUNT(*) as count FROM artworks");
    const [donationTotal] = await db.query("SELECT COALESCE(SUM(amount), 0) as total FROM donations");
    const [reviewCount] = await db.query("SELECT COUNT(*) as count FROM artist_reviews");

    return Response.json({
      users: userCount[0].count,
      artists: artistCount[0].count,
      artworks: artworkCount[0].count,
      totalDonations: donationTotal[0].total,
      reviews: reviewCount[0].count,
    });
  } catch (err) {
    return Response.json({ error: err.message }, { status: 500 });
  }
}
