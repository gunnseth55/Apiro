import {db} from "@/lib/db"
export async function GET(){
    try{
        const [rows]=await db.query(
            `SELECT world_art.*, countries.name as country_name 
            FROM world_art 
            JOIN countries ON world_art.country_id = countries.country_id
            ORDER BY countries.name ASC`
        )
        return Response.json(rows);
    }catch (err){
        return Response.json([])
    }
}