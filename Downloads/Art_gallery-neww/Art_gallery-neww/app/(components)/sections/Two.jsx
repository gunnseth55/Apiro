"use client";
import Image from "next/image";

export default function Two() {
  const content = [
    { id: 1, title: "Art1", source: "/assets/images/black_cat.jpg" },
    { id: 2, title: "Art2", source: "/assets/images/two.jpg" },
    { id: 3, title: "Art3", source: "/assets/images/download (2).jpg" },
    { id: 4, title: "Art4", source: "/assets/images/black.jpg" },
  ];

  return (
    <section className="py-16 md:py-24 px-6 md:px-12 lg:px-20">
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 items-center gap-8 lg:gap-12">
          {/* Image grid */}
          <div className="grid grid-cols-3 grid-rows-2 gap-3 md:gap-4 lg:gap-6 aspect-[6/5]">
            <div className="relative col-span-2 row-span-2 overflow-hidden rounded-xl">
              <Image
                src={content[0].source}
                alt={content[0].title}
                fill
                className="object-cover hover:scale-110 transition duration-500"
              />
            </div>
            <div className="relative overflow-hidden rounded-xl">
              <Image
                src={content[1].source}
                alt={content[1].title}
                fill
                className="object-cover hover:scale-110 transition duration-500"
              />
            </div>
            <div className="relative overflow-hidden rounded-xl">
              <Image
                src={content[2].source}
                alt={content[2].title}
                fill
                className="object-cover hover:scale-110 transition duration-500"
              />
            </div>
          </div>

          {/* Right side image */}
          <div className="flex justify-center">
            <Image
              src="/assets/images/artisty-removebg-preview.png"
              alt="Artistic illustration"
              width={500}
              height={400}
              className="object-cover w-full max-w-md"
            />
          </div>
        </div>
      </div>
    </section>
  );
}