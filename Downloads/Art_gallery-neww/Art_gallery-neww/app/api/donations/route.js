import {db} from "@/lib/db"
export async function POST(req){

    try{

            const {artist_id, user_id,amount}=await req.json();
            if(!amount || amount<=0){
                return Response.json({error:"Invalid Amount"},{status:400})
            }
            await db.query(
            "INSERT INTO donations (artist_id, user_id, amount) VALUES (?, ?, ?)",
            [artist_id, user_id, amount]
        );
        return Response.json({message:"Donation Successful!"});
    }catch(err){
        return Response.json({error:err.message},{status:500})
    }
}