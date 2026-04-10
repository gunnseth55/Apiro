import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center px-6">
      <div className="text-center animate-fade-in-up">
        <h1 className="text-[12rem] leading-none font-display font-bold text-amber-50/10 select-none">
          404
        </h1>
        <div className="-mt-16 relative z-10">
          <h2 className="text-4xl md:text-5xl font-display font-bold text-amber-50 mb-4">
            Lost in the Gallery
          </h2>
          <p className="text-gray-400 text-lg max-w-md mx-auto mb-10">
            The masterpiece you&apos;re looking for has wandered off.
            Let&apos;s get you back to the collection.
          </p>
          <Link
            href="/"
            className="inline-block bg-amber-50 text-black font-bold px-8 py-4 rounded-xl uppercase tracking-widest text-sm hover:bg-white transition-colors"
          >
            Return to Gallery
          </Link>
        </div>
      </div>
    </div>
  );
}
