"use client";
import Image from "next/image";
import { useState, useEffect } from "react";

export default function WishlistPage() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [viewerId, setViewerId] = useState(null);

  useEffect(() => {
    const vId = localStorage.getItem("viewer_id");
    setViewerId(vId);
    if (!vId) {
      setLoading(false);
      return;
    }

    fetch(`/api/wishlist?user_id=${vId}`)
      .then((res) => res.json())
      .then((json) => {
        setData(json);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Fetch error", err);
        setLoading(false);
      });
  }, []);

  const removeWishlist = async (artwork_id) => {
    try {
      const vId = localStorage.getItem("viewer_id");
      if (!vId) return;

      const res = await fetch("/api/wishlist", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: parseInt(vId),
          artwork_id: artwork_id,
        }),
      });
      if (res.ok) {
        setData(data.filter((item) => item.artwork_id !== artwork_id));
      }
    } catch (error) {
      console.error("Error removing from wishlist", error);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center pt-24">
        <div className="text-center animate-fade-in">
          <div className="spinner text-amber-50 mx-auto mb-4" style={{ width: 32, height: 32, borderWidth: 3 }} />
          <p className="text-gray-400 tracking-widest uppercase text-sm">Loading Wishlist...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black pt-24">
      {!viewerId ? (
        <div className="flex flex-col items-center justify-center py-32 text-white animate-fade-in-up">
          <div className="text-6xl mb-6 animate-float">🖼️</div>
          <h1 className="text-3xl font-display font-bold mb-3">Your Wishlist Awaits</h1>
          <p className="text-gray-400 text-lg mb-8 max-w-md text-center">
            Sign in to save your favorite masterpieces and build your personal collection.
          </p>
          <a
            href="/login"
            className="py-3 px-8 bg-amber-50 text-black font-bold uppercase tracking-widest rounded-xl hover:bg-amber-200 transition-colors"
          >
            Sign In
          </a>
        </div>
      ) : data.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-32 text-white animate-fade-in-up">
          <div className="text-6xl mb-6 animate-float">💫</div>
          <h1 className="text-3xl font-display font-bold mb-3">Your Wishlist is Empty</h1>
          <p className="text-gray-400 text-lg mb-8 max-w-md text-center">
            Start exploring and add artworks you love to your wishlist.
          </p>
          <a
            href="/world"
            className="py-3 px-8 bg-amber-50 text-black font-bold uppercase tracking-widest rounded-xl hover:bg-amber-200 transition-colors"
          >
            Explore Art
          </a>
        </div>
      ) : (
        <div className="animate-fade-in">
          {/* Hero Header */}
          <div className="text-center pt-8 pb-12 px-6">
            <h1 className="text-5xl md:text-6xl font-display font-bold text-amber-50 mb-3">
              My Wishlist
            </h1>
            <p className="text-gray-400 tracking-wider">
              {data.length} {data.length === 1 ? "masterpiece" : "masterpieces"} saved
            </p>
          </div>

          {/* Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8 px-6 md:px-10 max-w-7xl mx-auto pb-20">
            {data.map((item, idx) => (
              <div
                key={item.artwork_id}
                className="group bg-zinc-900/50 border border-white/5 rounded-2xl overflow-hidden hover:border-amber-50/20 transition-all duration-500 animate-fade-in-up"
                style={{ animationDelay: `${idx * 80}ms` }}
              >
                <div className="relative w-full h-72 bg-zinc-900 overflow-hidden">
                  <Image
                    src={item.image || "/file.svg"}
                    alt={item.title || "Artwork"}
                    fill
                    className="object-cover group-hover:scale-105 transition-transform duration-700"
                    unoptimized
                  />
                </div>
                <div className="p-5">
                  <h2 className="text-xl font-display font-bold text-amber-50 mb-4 truncate">
                    {item.title || "Untitled"}
                  </h2>
                  <button
                    onClick={() => removeWishlist(item.artwork_id)}
                    className="w-full py-2.5 bg-red-500/10 hover:bg-red-500 text-red-300 hover:text-white rounded-xl transition-all text-sm font-medium tracking-wider uppercase"
                  >
                    Remove from Wishlist
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}