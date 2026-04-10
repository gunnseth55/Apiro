"use client";
import { useState, useEffect } from "react";
import Image from "next/image";
import Wishlist from "../(components)/Wish.jsx";

export default function Vibes() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/world_arts")
      .then((res) => res.json())
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const groupedArt = data.reduce((acc, item) => {
    if (!acc[item.country_name]) acc[item.country_name] = [];
    acc[item.country_name].push(item);
    return acc;
  }, {});

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center pt-24">
        <div className="text-center animate-fade-in">
          <div className="spinner text-amber-50 mx-auto mb-4" style={{ width: 32, height: 32, borderWidth: 3 }} />
          <p className="text-gray-400 tracking-widest uppercase text-sm">Loading Global Collections...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-stone-200 pt-24 pb-20">
      {/* Hero */}
      <div className="text-center pt-8 pb-16 px-6 animate-fade-in">
        <h1 className="text-5xl md:text-7xl font-display font-bold text-amber-50 mb-3">
          Global Collections
        </h1>
        <p className="text-gray-400 tracking-wider text-lg max-w-xl mx-auto">
          Explore famous artworks from civilizations around the world.
        </p>
      </div>

      {Object.keys(groupedArt).map((country, groupIdx) => (
        <section
          key={country}
          className="mb-20 max-w-7xl mx-auto px-6 md:px-10 animate-fade-in-up"
          style={{ animationDelay: `${groupIdx * 150}ms` }}
        >
          <div className="flex items-center gap-4 mb-8 border-b border-white/10 pb-4">
            <h2 className="text-3xl md:text-4xl font-display font-bold text-amber-400">
              {country}
            </h2>
            <span className="text-xs text-gray-500 tracking-widest uppercase bg-white/5 px-3 py-1 rounded-full">
              {groupedArt[country].length} works
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6">
            {groupedArt[country].map((art, idx) => (
              <div
                key={art.art_id}
                className="group relative bg-zinc-900/50 rounded-2xl overflow-hidden border border-white/5 hover:border-amber-50/20 transition-all duration-500"
              >
                <div className="relative overflow-hidden w-full h-64">
                  <Image
                    src={art.image_url}
                    alt={art.title}
                    fill
                    className="object-cover transition-transform duration-700 group-hover:scale-110"
                    unoptimized
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                </div>

                <div className="absolute bottom-0 right-4 z-10 bg-black/60 p-2 rounded-full border border-gray-700 hover:border-amber-50/30 transition-colors opacity-0 group-hover:opacity-100 transition-all duration-300">
                  <Wishlist artworkId={art.art_id + 100000} />
                </div>

                <div className="p-5">
                  <h3 className="text-xl font-display font-semibold text-amber-50 mb-1">
                    {art.title}
                  </h3>
                  <p className="text-xs text-gray-500 uppercase tracking-widest">
                    {art.era}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}