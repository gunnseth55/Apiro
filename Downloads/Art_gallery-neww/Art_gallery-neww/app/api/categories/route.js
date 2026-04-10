import {db} from "@/lib/db"
export async function GET(){
    const [categories]=await db.query(
        "SELECT * FROM categories"
    );
    return Response.json(categories);
}