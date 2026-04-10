"use client";
import { useState } from "react";
import One from "./(components)/sections/One.jsx";
import Two from "./(components)/sections/Two.jsx";
import Three from "./(components)/sections/Three.jsx";
import Four from "./(components)/sections/Four.jsx";
import World from "./(components)/sections/World.jsx";

export default function Home() {
  const [mode, setMode] = useState(false);
  return (
    <div
      className={`transition-colors duration-700 ${
        mode ? "bg-amber-50 text-black" : "bg-black text-white"
      }`}
    >
      <One />
      <Two />
      <Three />
      <World setMode={setMode} />
      <Four />
    </div>
  );
}
