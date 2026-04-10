import {db} from "@/lib/db";
export async function GET(req){
  try {
    const { searchParams } = new URL(req.url);
    const user_id = searchParams.get("user_id");

    const [rows] = await db.query(
      `SELECT 
        wishlist.artwork_id, 
        COALESCE(artworks.title, categories.name, c1.name, c2.name, c3.name, world_art.title) AS title, 
        COALESCE(artworks.image_url, categories.image_url_1, c1.image_url_1, c2.image_url_2, c3.image_url_3, world_art.image_url) AS image
      FROM wishlist
      LEFT JOIN artworks ON wishlist.artwork_id = artworks.artwork_id
      LEFT JOIN categories ON wishlist.artwork_id = categories.category_id
      LEFT JOIN categories AS c1 ON wishlist.artwork_id = (c1.category_id + 1000000)
      LEFT JOIN categories AS c2 ON wishlist.artwork_id = (c2.category_id + 2000000)
      LEFT JOIN categories AS c3 ON wishlist.artwork_id = (c3.category_id + 3000000)
      LEFT JOIN world_art ON wishlist.artwork_id = (world_art.art_id + 100000)
      WHERE wishlist.user_id = ?`,
      [user_id]
    );

    return Response.json(rows);
  } catch (error) {
    console.error("Database Error:", error);
    return Response.json({ error: error.message }, { status: 500 });
  }
}

export async function POST(req){
   try {
        const { user_id, artwork_id } = await req.json();
        const [result] = await db.query(
            "INSERT INTO wishlist (user_id, artwork_id) VALUES (?, ?)",
            [user_id, artwork_id]
        );
        
        return Response.json({ message: "Added to wishlist", id: result.insertId });
    } catch (error) {
        console.error("Database Error:", error); 
        return Response.json({ error: error.message }, { status: 500 });
    }
}

export async function DELETE(req){
   try{
     const {user_id,artwork_id} =await req.json();
    await db.query(
        "DELETE FROM wishlist WHERE user_id=? AND artwork_id=?",
        [user_id,artwork_id]
    );
    return Response.json({message: "Removed from wishlist"});
   }
   catch(err){
    return Response.json({error:err.message},{status:500});
   }

}