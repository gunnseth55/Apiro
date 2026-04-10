"use client";
import { useState } from "react";

export default function Donations({ artistId, artistName }) {
  const [amount, setAmount] = useState("");
  const [status, setStatus] = useState("");

  const handleDonate = async (e) => {
    if (e) e.preventDefault();

    const viewer_id = localStorage.getItem("viewer_id");
    if (!viewer_id) {
      alert("Please Sign In as a general user to make a donation.");
      return;
    }

    const res = await fetch("/api/donations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        artist_id: artistId,
        user_id: parseInt(viewer_id),
        amount: parseFloat(amount),
      }),
    });

    if (res.ok) {
      setStatus("Success! Thank you for supporting " + artistName);
      setAmount("");
    } else {
      setStatus("Transaction failed. Please try again.");
    }
  };

  return (
    <div className="text-white px-4 sm:px-6 md:px-10 lg:px-20 xl:px-30 tracking-wider max-w-5xl mx-auto">
      <h2 className="text-3xl sm:text-4xl md:text-5xl font-display pb-2">
        Support {artistName}
      </h2>
      <p className="text-lg sm:text-xl md:text-2xl font-display pb-4 text-gray-300">
        Every contribution helps the artists keep creating
      </p>

      <div className="flex flex-wrap gap-2 sm:gap-3 mb-4">
        {[50, 100, 500, 1000].map((item) => (
          <button
            key={item}
            onClick={() => setAmount(item)}
            className={`flex-1 min-w-[70px] p-3 rounded-xl border transition-all text-sm sm:text-base ${
              amount == item
                ? "bg-amber-400 border-amber-400 text-black font-bold"
                : "border-gray-700 hover:border-amber-400"
            }`}
          >
            ₹{item}
          </button>
        ))}
      </div>

      <form onSubmit={handleDonate} className="space-y-4 pb-12 md:pb-20">
        <div className="relative border border-amber-50 rounded-2xl">
          <span className="absolute left-4 top-3 text-gray-500">₹</span>
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="Enter custom amount"
            className="w-full bg-transparent border-none p-3 pl-8 rounded-xl text-lg outline-none transition-colors"
          />
        </div>

        <button
          type="submit"
          disabled={!amount}
          className="w-full cursor-pointer bg-amber-50 text-black py-4 rounded-xl font-bold text-lg hover:bg-amber-200 transition-colors disabled:opacity-50"
        >
          Donate Now
        </button>
      </form>

      {status && (
        <p className="mt-4 text-center text-amber-400 animate-pulse">{status}</p>
      )}
    </div>
  );
}