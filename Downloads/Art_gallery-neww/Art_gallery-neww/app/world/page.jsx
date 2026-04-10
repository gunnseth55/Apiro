"use client";
import { useEffect, useState } from "react";
import Image from "next/image";
import Wishlist from "../(components)/Wish.jsx";

export default function World() {
  const [cat, setCat] = useState([]);
  const [loading, setLoading] = useState(true);
  const [show, setShow] = useState(null);

  useEffect(() => {
    async function fetchdata() {
      const res = await fetch("/api/categories", { cache: "no-store" });
      const data = await res.json();
      setCat(data);
      setLoading(false);
    }
    fetchdata();
  }, []);

  // Get the selected category for the slide-out panel
  const selectedCategory = cat.find((c) => c.category_id === show);

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center pt-24">
        <div className="text-center animate-fade-in">
          <div className="spinner text-amber-50 mx-auto mb-4" style={{ width: 32, height: 32, borderWidth: 3 }} />
          <p className="text-gray-400 tracking-widest uppercase text-sm">Loading Categories...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gradient-to-b from-zinc-900 via-black to-black min-h-screen">
      {/* Hero */}
      <div className="text-center pt-32 pb-12 px-6 animate-fade-in">
        <h1 className="text-5xl md:text-7xl font-display font-bold text-amber-50 mb-3">
          Explore Art
        </h1>
        <p className="text-gray-400 tracking-wider text-lg max-w-xl mx-auto">
          Browse through {cat.length} curated categories of art from across movements and eras.
        </p>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8 px-6 md:px-16 lg:px-32 pb-20 max-w-7xl mx-auto">
        {cat.map((item, idx) => (
          <div
            key={item.category_id}
            className="animate-fade-in-up"
            style={{ animationDelay: `${idx * 60}ms` }}
          >
            {/* Card */}
            <div className="group relative bg-zinc-900/50 rounded-2xl overflow-hidden border border-white/5 hover:border-amber-50/20 transition-all duration-500">
              <div className="relative w-full h-72 overflow-hidden">
                <Image
                  src={item.image_url_1}
                  fill
                  alt={item.name}
                  className="object-cover group-hover:scale-110 transition-transform duration-700"
                  unoptimized
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />
              </div>
              <div className="absolute bottom-0 left-0 right-0 p-6">
                <h2 className="text-2xl font-display font-bold text-white mb-1">
                  {item.name}
                </h2>
                <p className="text-gray-400 text-sm line-clamp-2 mb-4">
                  {item.description}
                </p>
                <button
                  onClick={() => setShow(item.category_id)}
                  className="text-sm text-amber-400 hover:text-amber-300 font-medium tracking-widest uppercase transition-colors"
                >
                  View Collection →
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Backdrop overlay on panel open */}
      {show !== null && (
        <div
          className="fixed inset-0 bg-black/50 z-[55]"
          onClick={() => setShow(null)}
        />
      )}

      {/* Single Slide-out Panel (rendered once, outside the grid) */}
      <div
        className={`fixed top-0 right-0 h-full w-full sm:w-2/3 md:w-1/2 bg-black/95 backdrop-blur-xl shadow-2xl transform transition-transform duration-500 overflow-y-auto z-[60] ${
          show !== null ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {selectedCategory && (
          <div className="p-6 md:p-8">
            <div className="sticky top-0 bg-black/90 backdrop-blur-md py-4 flex justify-between items-center z-10 mb-6 border-b border-white/10 pb-4">
              <h2 className="text-3xl font-display font-bold text-amber-50">
                {selectedCategory.name}
              </h2>
              <button
                onClick={() => setShow(null)}
                className="w-10 h-10 flex items-center justify-center rounded-full border border-white/10 hover:bg-white/10 text-white text-xl transition-colors"
              >
                ✕
              </button>
            </div>
            <p className="text-gray-300 text-lg mb-8 leading-relaxed">
              {selectedCategory.description}
            </p>
            {[selectedCategory.image_url_1, selectedCategory.image_url_2, selectedCategory.image_url_3].map((img, i) => (
              <div key={i} className="relative mb-8 group/img">
                <div className="relative w-full h-72 md:h-96 rounded-xl overflow-hidden bg-zinc-900">
                  <Image
                    src={img}
                    fill
                    className="object-contain p-2"
                    alt={`${selectedCategory.name} ${i + 1}`}
                    unoptimized
                  />
                </div>
                <div className="absolute bottom-4 right-4 z-10 bg-black/60 p-2 rounded-full border border-gray-700 hover:border-amber-50/40 transition-colors">
                  <Wishlist artworkId={selectedCategory.category_id + (i + 1) * 1000000} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}