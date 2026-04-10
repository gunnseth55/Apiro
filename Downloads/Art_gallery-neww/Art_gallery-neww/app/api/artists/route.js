import {db} from "@/lib/db"
export async function GET(){
    const [artists]=await db.query(
        "SELECT * FROM artists ORDER BY artist_id DESC"
    );
    return Response.json(artists);
}