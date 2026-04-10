"use client";
import Link from "next/link";
import { useEffect, useState } from "react";

export default function One() {
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setLoaded(true), 200);
    return () => clearTimeout(t);
  }, []);

  return (
    <section id="hero" className="relative h-screen w-full overflow-hidden">
      {/* Background Video */}
      <video
        autoPlay
        loop
        muted
        playsInline
        className="absolute top-0 left-0 w-full h-full object-cover"
      >
        <source src="/assets/videos/one.mp4" type="video/mp4" />
      </video>

      {/* Gradient Overlays */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/30 to-black/80" />
      <div className="absolute inset-0 bg-gradient-to-r from-black/40 to-transparent" />

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center justify-center h-full text-center px-6">
        {/* Subtitle */}
        <p
          className={`text-xs sm:text-sm tracking-[0.4em] uppercase text-amber-200/70 mb-4 transition-all duration-1000 ${
            loaded ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}
        >
          Discover · Collect · Experience
        </p>

        {/* Main Title */}
        <h1
          className={`text-5xl sm:text-6xl md:text-7xl lg:text-8xl xl:text-9xl font-display font-bold text-amber-50 leading-none mb-6 transition-all duration-1000 delay-200 ${
            loaded ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
        >
          Art Gallery
        </h1>

        {/* Tagline */}
        <p
          className={`text-base sm:text-lg md:text-xl text-gray-300 max-w-xl mb-10 leading-relaxed transition-all duration-1000 delay-500 ${
            loaded ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
          }`}
        >
          A curated digital home for extraordinary art from the world&apos;s most
          inspiring artists.
        </p>

        {/* CTA Buttons */}
        <div
          className={`flex flex-col sm:flex-row gap-4 transition-all duration-1000 delay-700 ${
            loaded ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
          }`}
        >
          <Link
            href="/world"
            className="px-8 py-4 bg-amber-50 text-black font-display font-bold uppercase tracking-widest rounded-xl hover:bg-white transition-colors text-sm"
          >
            Explore Gallery
          </Link>
          <Link
            href="/auth"
            className="px-8 py-4 border border-amber-50/30 text-amber-50 font-display uppercase tracking-widest rounded-xl hover:bg-amber-50/10 transition-colors text-sm"
          >
            Artist Portal
          </Link>
        </div>
      </div>

      {/* Scroll Indicator */}
      <div
        className={`absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 transition-all duration-1000 delay-1000 ${
          loaded ? "opacity-60" : "opacity-0"
        }`}
      >
        <span className="text-[10px] uppercase tracking-[0.3em] text-gray-400">
          Scroll
        </span>
        <div className="w-px h-8 bg-gradient-to-b from-gray-400 to-transparent animate-pulse" />
      </div>
    </section>
  );
}