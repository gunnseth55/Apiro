"use client";
import {useState, useRef, useEffect} from "react";
import { Swiper, SwiperSlide } from "swiper/react";
import { Autoplay } from "swiper/modules";
import Image from "next/image";
import "swiper/css";
import "swiper/css/autoplay";
import Link from "next/link";

export default function Three(){

     const swiperRef = useRef(null);
     const content=[
  {
    id:1,
    title:"Art1",
    source:"/assets/images/ll1.jpg",
   

  },
  { id:2,
    title:"Art2",
    source:"/assets/images/ll2.jpg",
   
},
{ id:3,
    title:"Art3",
    source:"/assets/images/ll3.jpg",
  
},
{ id:4,
    title:"Art4",
    source:"/assets/images/ll4.jpg",
   
},
{ id:5,
    title:"Art3",
    source:"/assets/images/ll5.jpg",
  
},
{ id:6,
    title:"Art4",
    source:"/assets/images/swan.jpg",
   
},
];
    return(
        <Link href="/world">
            <div className="relative w-full mt-30 mb-30">
              
             <div className="flex justify-center items-center ">
                <h1 className="text-9xl font-extralight ">
                  #ARTVERSE
                </h1>
                
              </div>
               <div className="flex justify-center items-center -mt-4">
                <h1 className="text-xl font-extralight ">
                  CHOOSE YOUR VIBE
                </h1>
                
              </div>

                <Swiper
            ref={swiperRef}
            modules={[Autoplay]}
            spaceBetween={16}
            slidesPerView={2}
            loop
            autoplay={{
              delay: 0,
              disableOnInteraction: false,
            }}
            speed={2000}
            breakpoints={{
              480: {
                slidesPerView: 1.2,
                spaceBetween: 16,
              },
              640: {
                slidesPerView: 2,
                spaceBetween: 20,
              },
              768: {
                slidesPerView: 3.5,
                spaceBetween: 20,
              },
              1024: {
                slidesPerView: 3.5,
                spaceBetween: 20,
              },
              1280: {
                slidesPerView: 3.5,
                spaceBetween: 20,
              },
            }}
            className="w-full "
          >
            {content.map((item,idx)=>(
                <SwiperSlide key={idx}>
                    <Image
                        src={item.source}
                        alt={item.title}
                        width={300}
                        height={300}
                        className=" w-full h-64 object-cover hover:scale-120 transition duration-700"
                      />
                </SwiperSlide>
            ))}
          </Swiper>
         
            </div>

        </Link>
    )
}
