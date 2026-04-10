"use client";
export default function Wishlist({artworkId})
{
const handleWishlist=async()=>{
  try{
    const viewer_id = localStorage.getItem("viewer_id");
    if (!viewer_id) {
       alert("Please Sign In to add art to your wishlist.");
       return;
    }
    
    await fetch("/api/wishlist",{
     method: "POST",
     body:JSON.stringify({
      user_id: parseInt(viewer_id),
      artwork_id:artworkId,
     }),
    });
    alert ("Added to wishlist");
  } catch (error){
    console.error("Error")
  }
};
   return (
    <button onClick={handleWishlist}
    className="text-2xl z-50 hover:scale-110 transition-transform"
    >
      ❤️
    </button>
   );
}
