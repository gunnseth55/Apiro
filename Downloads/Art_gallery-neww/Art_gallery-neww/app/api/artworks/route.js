import {db} from "@/lib/db"
export async function GET(req){

    const { searchParams }=new URL(req.url);
    const artist_id=searchParams.get("artist_id");
    let query= "SELECT * from artworks";
    let values=[];
    if(artist_id){
        query +=" WHERE artist_id =?";
        values.push(artist_id);
    }

    const [artworks]=await db.query(
        query,values
    );
    return Response.json(artworks);
}