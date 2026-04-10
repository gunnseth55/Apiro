import {db} from "@/lib/db"
export async function GET(){
    const [rows]=await db.query("SELECT 1");
    return Response.json({
        message: "Database connected successfully"
    });
}