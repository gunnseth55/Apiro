"use client";
import { useState, useEffect } from "react";

export default function Review({ artistId }) {
  const [review, setReview] = useState([]);
  const [comment, setComment] = useState("");
  const [rating, setRating] = useState(5);

  const fetchReviews = async () => {
    const res = await fetch(`/api/review?artist_id=${artistId}`);
    if (!res.ok) {
      const errorText = await res.text();
      console.error(`Server Error (${res.status}):`, errorText);
      try {
        const errorData = JSON.parse(errorText);
        console.error("Parsed API Error:", errorData);
      } catch (e) {
        console.error("Server sent non-JSON error (likely a 500 crash page)");
      }
      return;
    }
    const data = await res.json();
    setReview(data);
  };

  useEffect(() => {
    if (artistId) fetchReviews();
  }, [artistId]);

  const handlesubmit = async (e) => {
    e.preventDefault();
    const viewer_id = localStorage.getItem("viewer_id");
    if (!viewer_id) {
      alert("Please Sign In to leave a review.");
      return;
    }

    await fetch("/api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        artist_id: artistId,
        user_id: parseInt(viewer_id),
        rating: rating,
        comment: comment,
      }),
    });
    setComment("");
    fetchReviews();
  };

  return (
    <div className="text-white px-4 sm:px-6 md:px-10 lg:px-20 xl:px-30 max-w-5xl mx-auto">
      <h1 className="text-3xl sm:text-4xl md:text-5xl font-display pb-4 pt-8">
        Add your review
      </h1>

      <form onSubmit={handlesubmit} className="space-y-4">
        <div className="flex justify-center sm:justify-start">
          {[1, 2, 3, 4, 5].map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setRating(item)}
              className="text-2xl sm:text-3xl text-amber-300 hover:scale-110 transition-transform px-0.5"
            >
              {item <= rating ? "★" : "☆"}
            </button>
          ))}
        </div>

        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Write your thoughts about the artist"
          className="w-full p-3 bg-black border border-gray-700 rounded-xl mb-4 focus:border-amber-50/40 outline-none transition-colors"
          rows={3}
        />

        <div className="flex justify-center sm:justify-start">
          <button
            type="submit"
            className="bg-amber-50 text-black py-2.5 px-8 rounded-xl hover:bg-amber-200 transition-colors font-bold tracking-widest uppercase text-sm"
          >
            Post Review
          </button>
        </div>
      </form>

      <div className="space-y-4 pb-16 md:pb-20 pt-8">
        <h1 className="text-3xl sm:text-4xl md:text-5xl font-display pb-4 md:pb-8">
          Published Reviews
        </h1>

        {review.length === 0 && (
          <p className="text-gray-500 text-center py-8">
            No reviews yet. Be the first to share your thoughts!
          </p>
        )}

        {review.map((item) => (
          <div key={item.review_id}>
            <div className="border border-amber-50/20 p-4 sm:p-5 rounded-xl hover:border-amber-50/40 transition-colors">
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
                <span className="font-bold text-lg sm:text-xl">
                  {item.user_name}
                </span>
                <span className="text-sm text-gray-500">
                  {new Date(item.created_at).toLocaleDateString()}
                </span>
              </div>
              <div className="text-yellow-500 text-lg mt-1">
                {"★".repeat(item.rating)}
                {"☆".repeat(5 - item.rating)}
              </div>
              {item.comment && (
                <p className="mt-2 text-gray-300 leading-relaxed">
                  {item.comment}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
