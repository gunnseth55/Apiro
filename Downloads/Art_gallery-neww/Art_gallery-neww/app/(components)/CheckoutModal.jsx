"use client";
import { useState } from "react";

export default function CheckoutModal({ artwork, onClose, onSuccess }) {
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");

  const handleCheckout = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch("/api/artworks/buy", {
         method: "POST",
         headers: { "Content-Type": "application/json" },
         body: JSON.stringify({ artwork_id: artwork.artwork_id, buyer_name: name, shipping_address: address })
      });
      const data = await res.json();
      if (res.ok) {
         onSuccess(artwork.artwork_id);
      } else {
         alert(data.error || "Transaction failed! Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-black border border-amber-50/20 max-w-lg w-full rounded-2xl p-8 relative shadow-2xl">
        <button onClick={onClose} className="absolute top-4 right-6 text-gray-500 hover:text-white text-3xl font-light">&times;</button>
        <h2 className="text-4xl font-serif text-amber-50 mb-2">Secure Checkout</h2>
        <p className="text-gray-400 mb-6 border-b border-gray-800 pb-4">
            Acquiring: <span className="text-white font-serif">{artwork.title}</span>
        </p>
        
        <form onSubmit={handleCheckout} className="space-y-5">
           <div>
              <label className="block text-xs font-bold tracking-widest text-gray-400 mb-2">BILLING NAME</label>
              <input required value={name} onChange={e=>setName(e.target.value)} type="text" className="w-full bg-transparent border border-gray-700 rounded-lg p-3 text-white focus:border-amber-50 outline-none transition" placeholder="John Doe" />
           </div>
           <div>
              <label className="block text-xs font-bold tracking-widest text-gray-400 mb-2">SHIPPING ADDRESS</label>
              <textarea required value={address} onChange={e=>setAddress(e.target.value)} rows={3} className="w-full bg-transparent border border-gray-700 rounded-lg p-3 text-white focus:border-amber-50 outline-none transition" placeholder="123 Gallery Lane, New York, NY 10001" />
           </div>
           
           <div className="pt-4">
             <button disabled={loading} type="submit" className="w-full bg-amber-50 text-black font-bold tracking-widest py-4 rounded-xl hover:bg-white transition flex justify-center items-center">
                {loading ? "PROCESSING..." : `PAY ₹${artwork.price}`}
             </button>
           </div>
           <p className="text-center text-xs text-gray-600 mt-4 flex items-center justify-center gap-2">
             <span>🔒 256-bit Secure Encrypted Connection</span>
           </p>
        </form>
      </div>
    </div>
  )
}
