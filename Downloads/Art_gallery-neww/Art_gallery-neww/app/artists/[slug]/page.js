import Wishlist from "../../(components)/Wish.jsx";
import Review from "../../(components)/Review.jsx";
import Donations from "../../(components)/Donations.jsx";
import PurchaseButton from "../../(components)/PurchaseButton.jsx";
import Image from "next/image";
import { db } from "@/lib/db";

export default async function ArtistProfile({ params }) {
  const { slug } = await params;

  // Directly query the database from the Server Component for blazing fast, prod-ready data
  const [artists] = await db.query("SELECT * FROM artists WHERE slug = ?", [slug]);
  const artist = artists[0];

  if (!artist) {
    return (
      <div className="p-20 text-center text-white min-h-screen bg-black pt-32 text-2xl font-serif">
        Artist not found.
      </div>
    );
  }

  const [artworks] = await db.query(
    "SELECT * FROM artworks WHERE artist_id = ? ORDER BY created_at DESC",
    [artist.artist_id]
  );

  return (
    <div className="bg-black">
      {/* Hero Video Background */}
      <section className="h-[40vh] sm:h-[50vh] relative overflow-hidden">
        <video
          autoPlay
          loop
          muted
          playsInline
          className="absolute top-0 left-0 w-full h-full object-cover"
        >
          <source src="/assets/videos/bb.mp4" type="video/mp4" />
        </video>
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/30 to-transparent" />
        <h1 className="px-4 sm:px-6 text-4xl sm:text-5xl md:text-7xl lg:text-8xl xl:text-9xl pb-2 text-amber-50 font-display tracking-widest text-center whitespace-nowrap absolute bottom-0 w-full overflow-hidden text-ellipsis">
          {artist.name}
        </h1>
      </section>

      {/* Artist Info Card */}
      <section className="pb-12 md:pb-20 relative px-4 sm:px-6 md:px-10">
        <div className="flex justify-center pt-6 md:pt-8">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4 md:gap-6 items-start rounded-2xl bg-amber-50/10 max-w-5xl w-full overflow-hidden">
            <div className="md:col-span-1">
              <Image
                src={artist.profile_image}
                alt={artist.name}
                width={200}
                height={200}
                unoptimized={true}
                className="object-cover w-full h-48 md:h-auto"
              />
            </div>
            <div className="text-gray-50 md:col-span-4 p-4 md:pt-6 md:px-4">
              <p className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-display font-bold">
                Nationality: {artist.country}
              </p>
              <p className="text-base sm:text-lg md:text-xl lg:text-2xl pt-4 md:pt-6 leading-relaxed">
                {artist.biography}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Artworks Section */}
      <section className="px-4 sm:px-6 md:px-10 lg:px-20 pb-12 md:pb-20 relative">
        <div className="bg-amber-50/10 p-4 sm:p-6 md:p-8 lg:p-10 rounded-xl max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-display text-amber-50 mb-6 md:mb-8 border-b border-amber-50/20 pb-4">
            Artworks
            {artworks.length > 0 && (
              <span className="text-base text-gray-500 ml-3">
                {artworks.length} {artworks.length === 1 ? "piece" : "pieces"}
              </span>
            )}
          </h2>

          <div className="space-y-6">
            {artworks.map((item) => (
              <div
                key={item.artwork_id}
                className="bg-black rounded-xl overflow-hidden shadow-lg hover:scale-[1.01] transition duration-700 p-3 sm:p-4"
              >
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6 py-4 sm:py-6 md:py-8 px-3 sm:px-4 md:px-8">
                  {/* Artwork Image */}
                  <div className="relative w-full h-64 sm:h-72 md:h-80 lg:h-96">
                    <Image
                      src={item.image_url}
                      alt={item.title}
                      fill
                      unoptimized={true}
                      className="absolute object-contain rounded-2xl z-0 bg-black/50"
                    />
                    <div className="absolute bottom-4 right-4 z-10 bg-black/60 p-2 rounded-full border border-gray-700 hover:border-amber-50/40 transition-colors">
                      <Wishlist artworkId={item.artwork_id} />
                    </div>
                  </div>

                  {/* Artwork Details */}
                  <div className="text-white px-2 sm:px-4 md:px-6 lg:px-10 py-4 md:py-6">
                    <p className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-semibold font-display">
                      {item.title}
                    </p>
                    <p className="pt-3 md:pt-6 text-xs text-gray-500 tracking-widest uppercase">
                      CREATED AT: {new Date(item.created_at).toLocaleDateString()}
                    </p>
                    <p className="text-base md:text-lg lg:text-xl mt-3 md:mt-4 mb-6 md:mb-8 text-gray-300 leading-relaxed">
                      {item.description || "No description provided."}
                    </p>

                    <div className="mt-auto border-t border-gray-800 pt-6 md:pt-8">
                      <p className="text-2xl sm:text-3xl md:text-4xl text-amber-50 font-bold mb-4 md:mb-6">
                        ₹{Number(item.price).toLocaleString()}
                      </p>
                      <PurchaseButton artwork={item} />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {artworks.length === 0 && (
            <div className="text-center py-16">
              <div className="text-5xl mb-4">🎨</div>
              <p className="text-gray-400 text-xl font-display">No artworks uploaded yet.</p>
            </div>
          )}
        </div>
      </section>

      {/* Donations Section */}
      <section className="relative z-10 pt-10 border-t border-gray-800">
        <Donations artistId={artist.artist_id} artistName={artist.name} />
      </section>

      {/* Reviews Section */}
      <Review artistId={artist.artist_id} />
    </div>
  );
}