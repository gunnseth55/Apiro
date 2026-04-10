import {db} from "@/lib/db";

export async function GET(req){
    try {
        const { searchParams } = new URL(req.url);
        const artist_id = searchParams.get("artist_id");
        
        if (!artist_id) return Response.json({error: "artist_id is required"}, {status: 400});

        // 1. Get total amount donated to this artist
        const [totalRes] = await db.query(
            "SELECT SUM(amount) as total FROM donations WHERE artist_id = ?", 
            [artist_id]
        );
        const total = totalRes[0]?.total || 0;

        // 2. Get chronological history of donations with user names
        const [history] = await db.query(
            `SELECT d.donation_id, d.amount, d.donated_at, u.name as user_name 
             FROM donations d
             JOIN users u ON d.user_id = u.user_id
             WHERE d.artist_id = ?
             ORDER BY d.donated_at DESC`,
            [artist_id]
        );

        return Response.json({ total, history });
    } catch (err) {
        return Response.json({ error: err.message }, { status: 500 });
    }
}
