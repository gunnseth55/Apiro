""
import {db} from "@/lib/db"
export async function GET(req){
   try {
    const { searchParams } = new URL(req.url);
    const artist_id = searchParams.get("artist_id");

    if (!artist_id) return Response.json([]);

    const [rows] = await db.query(
      `SELECT artist_reviews.*, users.name as user_name
   FROM artist_reviews
   JOIN users ON artist_reviews.user_id = users.user_id
   WHERE artist_reviews.artist_id = ?
   ORDER BY created_at DESC`,
  [artist_id]
    );

    return Response.json(rows);
  } catch (error) {
    console.error("GET Error:", error);
    return Response.json({ error: error.message }, { status: 500 });
  }
}

export async function POST(req){
try{
    const {artist_id, user_id, rating,comment}=await req.json();
    await db.query(
        "INSERT INTO artist_reviews (artist_id,user_id,rating,comment) VALUES (?,?,?,?)",
        [artist_id,user_id,rating,comment]
    );
    return Response.json({message:"Review Added!"})

}
catch(err){
    return Response.json({error:err.message},{status:500});
}
}