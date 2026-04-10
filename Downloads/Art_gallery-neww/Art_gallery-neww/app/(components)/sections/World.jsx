"use client";
import { FaChevronCircleRight } from "react-icons/fa";
import Image from "next/image";
import { useEffect, useRef } from "react";
import Link from "next/link";

export default function World({ setMode }) {
  const ref = useRef(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        setMode(entry.isIntersecting);
      },
      { threshold: 0.4 }
    );

    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [setMode]);

  return (
    <section ref={ref} className="px-6 md:px-16 lg:px-24 xl:px-40 py-16 md:py-24">
      <div className="max-w-7xl mx-auto">
        <div>
          <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-semibold leading-tight">
            UNCOVER WORLD ARTS
          </h1>
          <h3 className="tracking-widest text-base md:text-lg lg:text-xl mt-2">
            see the famous art from the world
          </h3>
        </div>

        <div className="flex flex-col sm:flex-row justify-center gap-4 md:gap-8 lg:gap-10 mt-8">
          <div className="relative w-full sm:w-1/2 aspect-[4/3] overflow-hidden rounded-xl">
            <Image
              src="/assets/images/greek.jpg"
              alt="Greek Art"
              fill
              className="object-cover hover:scale-105 transition duration-700"
            />
          </div>
          <div className="relative w-full sm:w-1/2 aspect-[4/3] overflow-hidden rounded-xl">
            <Image
              src="/assets/images/madhubani.jpg"
              alt="Madhubani Painting"
              fill
              className="object-cover hover:scale-105 transition duration-700"
            />
          </div>
        </div>

        <Link href="/vibes">
          <div className="flex justify-center items-center mt-6 md:mt-8">
            <FaChevronCircleRight className="text-3xl md:text-4xl hover:scale-110 transition duration-500" />
          </div>
        </Link>
      </div>
    </section>
  );
}