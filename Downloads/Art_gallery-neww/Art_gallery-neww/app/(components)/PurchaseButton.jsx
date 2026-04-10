"use client";
import { useState } from "react";
import CheckoutModal from "./CheckoutModal";

export default function PurchaseButton({ artwork }) {
    const [showModal, setShowModal] = useState(false);
    // Control state via is_sold from the database directly!
    const [sold, setSold] = useState(artwork.is_sold === 1 || artwork.is_sold === true);

    const handleSuccess = () => {
        setShowModal(false);
        setSold(true);
    };

    if (sold) {
       return (
       <div className="flex justify-center items-center w-full mt-2">
            <button disabled className="cursor-not-allowed bg-red-900/20 border border-red-900/50 text-red-500 py-3 px-8 rounded-full w-full font-bold tracking-widest uppercase shadow-inner">
                Sold Out
            </button>
       </div>
       )
    }

    return (
       <div className="flex justify-center items-center w-full mt-2">
         <button onClick={() => setShowModal(true)} className="cursor-pointer bg-amber-400 text-black font-bold py-3 px-8 rounded-full hover:bg-amber-300 transition-colors w-full tracking-widest uppercase">
            Buy Now
         </button>
         {showModal && <CheckoutModal artwork={artwork} onClose={() => setShowModal(false)} onSuccess={handleSuccess} />}
       </div>
    )
}
