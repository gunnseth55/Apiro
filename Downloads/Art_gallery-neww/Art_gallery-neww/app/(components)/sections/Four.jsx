"use client";
import Image from "next/image";
import { useState, useEffect, useRef } from "react";
import { Swiper, SwiperSlide } from "swiper/react";
import { Autoplay, Navigation } from "swiper/modules";
import "swiper/css";
import "swiper/css/autoplay";
import "swiper/css/navigation";
import Link from "next/link";

export default function Four() {
  const swiperRef = useRef(null);
  const [artists, setArtists] = useState([]);
  const [swiperInstance, setSwiperInstance] = useState(null);

  useEffect(() => {
  fetch("/api/artists")
    .then((res) => {
      if (!res.ok) throw new Error("API error");
      return res.json();
    })
    .then((data) => setArtists(data))
    .catch((err) => console.error(err));
}, []);

  return (
    <>
      <section className="sticky top-0 h-screen flex justify-center items-center px-6">
        <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold border-t-2 border-t-amber-50 border-b-2 border-b-amber-50 p-2 text-center">
          ALL STILLS
        </h1>
      </section>

      <section className="relative min-h-screen bg-amber-50 pb-16">
        <div className="flex justify-center items-center px-6">
          <h1 className="text-black text-3xl sm:text-4xl md:text-5xl lg:text-6xl mt-16 sm:mt-20 md:mt-24 lg:mt-30 mb-12 sm:mb-16 md:mb-20 lg:mb-30 font-semibold border-t-2 border-t-black border-b-2 border-b-black text-center">
            ARTISTS WE LOVE
          </h1>
        </div>

        <div className="relative px-4">
          <Swiper
            ref={swiperRef}
            key={artists.length}
            modules={[Autoplay, Navigation]}
            onSwiper={setSwiperInstance}
            navigation
            spaceBetween={16}
            slidesPerView={2}
            loop={true}
            autoplay={{
              delay: 2000,
              disableOnInteraction: false,
            }}
            speed={800}
            breakpoints={{
              480: { slidesPerView: 3, spaceBetween: 10 },
              640: { slidesPerView: 3.5, spaceBetween: 10 },
              768: { slidesPerView: 5, spaceBetween: 10 },
              1024: { slidesPerView: 5, spaceBetween: 10 },
              1280: { slidesPerView: 5, spaceBetween: 10 },
            }}
            className="w-full"
          >
            {artists.map((item) => (
              <SwiperSlide key={item.artist_id}>
                <Link href={`/artists/${item.slug}`}>
                  <div className="cursor-pointer h-[200px] sm:h-[250px] md:h-[300px] overflow-hidden rounded-lg">
                    <Image
                      src={item.profile_image}
                      alt={item.name}
                      width={400}
                      height={400}
                      className="w-full h-full object-cover hover:scale-105 transition duration-500"
                    />
                  </div>
                </Link>
                <p className="mt-2 text-center text-black font-semibold text-sm sm:text-base">
                  {item.name}
                </p>
              </SwiperSlide>
            ))}
          </Swiper>
        </div>
      </section>
    </>
  );
}