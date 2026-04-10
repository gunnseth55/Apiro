"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";

export default function Dashboard() {
  const router = useRouter();
  const [artistId, setArtistId] = useState(null);
  const [artistName, setArtistName] = useState("");
  const [artworks, setArtworks] = useState([]);
  const [categories, setCategories] = useState([]);
  const [donations, setDonations] = useState({ total: 0, history: [] });
  const [orders, setOrders] = useState([]);

  // Form State
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [artworkFile, setArtworkFile] = useState(null);
  const [price, setPrice] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(false);

  // Edit Profile state
  const [showEditProfile, setShowEditProfile] = useState(false);
  const [editName, setEditName] = useState("");
  const [editBio, setEditBio] = useState("");
  const [editCountry, setEditCountry] = useState("");
  const [editProfileFile, setEditProfileFile] = useState(null);
  const [isSavingProfile, setIsSavingProfile] = useState(false);

  // Delete state
  const [deletingId, setDeletingId] = useState(null);

  useEffect(() => {
    const storedArtistId = localStorage.getItem("artist_id");
    const storedArtistName = localStorage.getItem("artist_name");

    if (!storedArtistId) {
      router.push("/auth");
    } else {
      setArtistId(storedArtistId);
      setArtistName(storedArtistName);
      fetchArtworks(storedArtistId);
      fetchCategories();
      fetchDonations(storedArtistId);
      fetchOrders(storedArtistId);
    }
  }, [router]);

  const fetchArtworks = async (id) => {
    const res = await fetch(`/api/artworks?artist_id=${id}`);
    if (res.ok) {
      const data = await res.json();
      setArtworks(data);
    }
  };

  const fetchCategories = async () => {
    const res = await fetch("/api/categories");
    if (res.ok) {
      const data = await res.json();
      setCategories(data);
    }
  };

  const fetchDonations = async (id) => {
    const res = await fetch(`/api/donations/history?artist_id=${id}`);
    if (res.ok) {
      const data = await res.json();
      setDonations(data);
    }
  };

  const fetchOrders = async (id) => {
    try {
      const res = await fetch(`/api/artists/orders?artist_id=${id}`);
      if (res.ok) {
        const data = await res.json();
        setOrders(data);
      }
    } catch (err) {
      console.error("Error fetching orders:", err);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("artist_id");
    localStorage.removeItem("artist_name");
    router.push("/auth");
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    setIsUploading(true);
    setUploadSuccess(false);

    try {
      if (!artworkFile) throw new Error("Please select an image file to upload");
      if (artworkFile.size > 5 * 1024 * 1024) throw new Error("File size must be under 5MB");

      // 1. Upload the artwork image
      const formData = new FormData();
      formData.append("file", artworkFile);

      const uploadRes = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      const uploadData = await uploadRes.json();
      if (!uploadRes.ok) throw new Error(uploadData.error || "Image upload failed");

      // 2. Submit artwork details
      const res = await fetch("/api/artworks/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          artist_id: artistId,
          title,
          description,
          image_url: uploadData.url,
          price: parseFloat(price),
          category_id: parseInt(categoryId),
        }),
      });

      if (!res.ok) throw new Error("Artwork submission failed");

      setUploadSuccess(true);
      setTitle("");
      setDescription("");
      setArtworkFile(null);
      setPrice("");
      setCategoryId("");
      fetchArtworks(artistId);

      setTimeout(() => setUploadSuccess(false), 3000);
    } catch (err) {
      alert(err.message);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteArtwork = async (artworkId) => {
    if (!confirm("Are you sure you want to delete this artwork? This cannot be undone.")) return;
    setDeletingId(artworkId);
    try {
      const res = await fetch("/api/artworks/delete", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ artist_id: parseInt(artistId), artwork_id: artworkId }),
      });
      if (res.ok) {
        setArtworks(artworks.filter((a) => a.artwork_id !== artworkId));
      } else {
        const data = await res.json();
        alert(data.error || "Failed to delete artwork");
      }
    } catch (err) {
      alert("Error deleting artwork");
    } finally {
      setDeletingId(null);
    }
  };

  const handleSaveProfile = async (e) => {
    e.preventDefault();
    setIsSavingProfile(true);
    try {
      let profileImageUrl = undefined;
      if (editProfileFile) {
        if (editProfileFile.size > 5 * 1024 * 1024) throw new Error("Profile image must be under 5MB");
        const formData = new FormData();
        formData.append("file", editProfileFile);
        const uploadRes = await fetch("/api/upload", { method: "POST", body: formData });
        const uploadData = await uploadRes.json();
        if (!uploadRes.ok) throw new Error(uploadData.error || "Image upload failed");
        profileImageUrl = uploadData.url;
      }

      const res = await fetch("/api/auth/update-artist", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          artist_id: artistId,
          name: editName || undefined,
          biography: editBio || undefined,
          country: editCountry || undefined,
          profile_image: profileImageUrl,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      if (editName) {
        setArtistName(editName);
        localStorage.setItem("artist_name", editName);
      }
      alert("Profile updated!");
      setShowEditProfile(false);
      setEditName("");
      setEditBio("");
      setEditCountry("");
      setEditProfileFile(null);
    } catch (err) {
      alert(err.message);
    } finally {
      setIsSavingProfile(false);
    }
  };

  if (!artistId)
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="spinner text-amber-50" style={{ width: 32, height: 32, borderWidth: 3 }} />
      </div>
    );

  return (
    <div className="min-h-screen bg-black text-amber-50 pt-28 px-6 md:px-10 pb-20">
      <div className="max-w-7xl mx-auto flex flex-col lg:flex-row gap-10">
        {/* Left Side: Upload Form */}
        <div className="w-full lg:w-1/3">
          <div className="glass p-8 rounded-2xl lg:sticky lg:top-28">
            <h2 className="text-3xl font-display mb-2">My Studio</h2>
            <p className="text-gray-400 mb-6">Welcome back, {artistName}.</p>

            <div className="flex gap-3 mb-6">
              <button
                onClick={handleLogout}
                className="text-red-400 hover:text-red-300 text-xs tracking-widest uppercase hover:bg-red-500/10 px-3 py-1.5 rounded-full transition-colors border border-red-500/20"
              >
                Logout
              </button>
              <button
                onClick={() => setShowEditProfile(!showEditProfile)}
                className="text-amber-400/70 hover:text-amber-400 text-xs tracking-widest uppercase hover:bg-amber-500/10 px-3 py-1.5 rounded-full transition-colors border border-amber-500/20"
              >
                {showEditProfile ? "Cancel" : "Edit Profile"}
              </button>
            </div>

            {showEditProfile && (
              <form onSubmit={handleSaveProfile} className="space-y-4 mb-8 border-b border-amber-50/10 pb-8">
                <h3 className="text-lg font-display border-b border-amber-50/10 pb-2 mb-4">Edit Profile</h3>
                <div>
                  <label className="block text-xs font-medium mb-1 tracking-wider text-gray-300">DISPLAY NAME</label>
                  <input value={editName} onChange={(e) => setEditName(e.target.value)} type="text" className="w-full bg-black border border-gray-600 focus:border-amber-50 rounded-lg p-2.5 outline-none transition-colors" placeholder={artistName} />
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1 tracking-wider text-gray-300">BIOGRAPHY</label>
                  <textarea rows={3} value={editBio} onChange={(e) => setEditBio(e.target.value)} className="w-full bg-black border border-gray-600 focus:border-amber-50 rounded-lg p-2.5 outline-none transition-colors" placeholder="Your artistic story..." />
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1 tracking-wider text-gray-300">COUNTRY</label>
                  <input value={editCountry} onChange={(e) => setEditCountry(e.target.value)} type="text" className="w-full bg-black border border-gray-600 focus:border-amber-50 rounded-lg p-2.5 outline-none transition-colors" placeholder="Italy" />
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1 tracking-wider text-gray-300">PROFILE PICTURE</label>
                  <input type="file" accept="image/*" onChange={(e) => setEditProfileFile(e.target.files[0])} className="w-full bg-black border border-gray-600 rounded-lg p-2 outline-none file:mr-3 file:py-1 file:px-3 file:rounded-full file:border-0 file:text-xs file:bg-amber-50 file:text-black" />
                </div>
                <button type="submit" disabled={isSavingProfile} className="w-full py-2.5 bg-amber-400 text-black font-bold rounded-xl text-sm tracking-widest hover:bg-amber-300 transition-colors disabled:opacity-50">
                  {isSavingProfile ? "SAVING..." : "SAVE CHANGES"}
                </button>
              </form>
            )}

            <h3 className="text-xl font-display mb-6 border-b border-amber-50/10 pb-2">Upload New Artwork</h3>

            {uploadSuccess && (
              <div className="bg-green-500/10 border border-green-500/30 text-green-400 p-3 rounded-xl mb-4 text-sm text-center animate-fade-in">
                ✓ Artwork uploaded successfully!
              </div>
            )}

            <form onSubmit={handleUpload} className="space-y-4">
              <div>
                <label className="block text-xs font-medium mb-1 tracking-wider text-gray-300">TITLE *</label>
                <input required value={title} onChange={(e) => setTitle(e.target.value)} type="text" className="w-full bg-black border border-gray-600 focus:border-amber-50 rounded-lg p-2.5 outline-none transition-colors" placeholder="Mona Lisa" />
              </div>

              <div>
                <label className="block text-xs font-medium mb-1 tracking-wider text-gray-300">UPLOAD IMAGE *</label>
                <input
                  required
                  type="file"
                  accept="image/*"
                  onChange={(e) => setArtworkFile(e.target.files[0])}
                  className="w-full bg-black border border-gray-600 focus:border-amber-50 rounded-lg p-2 outline-none file:mr-4 file:py-1 file:px-4 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-amber-50 file:text-black hover:file:bg-amber-100"
                />
                <p className="text-xs text-gray-600 mt-1">Max file size: 5MB</p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium mb-1 tracking-wider text-gray-300">PRICE (₹) *</label>
                  <input required value={price} onChange={(e) => setPrice(e.target.value)} type="number" step="0.01" min="0" className="w-full bg-black border border-gray-600 focus:border-amber-50 rounded-lg p-2.5 outline-none transition-colors" placeholder="5000" />
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1 tracking-wider text-gray-300">CATEGORY *</label>
                  <select required value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className="w-full bg-black border border-gray-600 focus:border-amber-50 rounded-lg p-2.5 outline-none transition-colors">
                    <option value="" disabled>Select...</option>
                    {categories.map((cat) => (
                      <option key={cat.category_id} value={cat.category_id}>{cat.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium mb-1 tracking-wider text-gray-300">DESCRIPTION</label>
                <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} className="w-full bg-black border border-gray-600 focus:border-amber-50 rounded-lg p-2.5 outline-none transition-colors" placeholder="Describe the piece..." />
              </div>

              <button type="submit" disabled={isUploading} className="w-full py-3 bg-amber-50 text-black font-display font-bold tracking-widest hover:bg-white transition-colors rounded-xl mt-2 disabled:opacity-50 flex items-center justify-center gap-2">
                {isUploading ? (
                  <>
                    <span className="spinner" style={{ width: 16, height: 16 }} />
                    UPLOADING...
                  </>
                ) : (
                  "PUBLISH ARTWORK"
                )}
              </button>
            </form>
          </div>
        </div>

        {/* Right Side: Donations & Portfolio */}
        <div className="w-full lg:w-2/3 space-y-10">
          {/* Donations Card */}
          <div className="glass p-8 rounded-2xl animate-fade-in">
            <h2 className="text-3xl font-display mb-2">Total Support Received</h2>
            <p className="text-5xl font-bold text-amber-400 mb-6">₹{donations.total}</p>
            {donations.history.length > 0 ? (
              <div className="space-y-3 max-h-60 overflow-y-auto pr-2">
                {donations.history.map((d) => (
                  <div key={d.donation_id} className="flex justify-between items-center bg-black/50 p-4 rounded-xl border border-white/5 hover:border-amber-50/20 transition-colors">
                    <div>
                      <p className="font-bold text-lg">{d.user_name}</p>
                      <p className="text-xs text-gray-500">{new Date(d.donated_at).toLocaleDateString()}</p>
                    </div>
                    <p className="text-2xl font-bold text-amber-50">₹{d.amount}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-500 text-sm">No donations received yet. Keep creating!</p>
            )}
          </div>

          {/* Order History */}
          <div className="glass p-8 rounded-2xl animate-fade-in" style={{ animationDelay: "100ms" }}>
            <h2 className="text-3xl font-display mb-2">Order History</h2>
            <p className="text-gray-500 text-sm mb-6">Artworks that have been purchased</p>
            {orders.length > 0 ? (
              <>
                <div className="space-y-3 max-h-80 overflow-y-auto pr-2">
                  {orders.map((o) => (
                    <div key={o.order_id} className="flex items-center gap-4 bg-black/50 p-4 rounded-xl border border-white/5 hover:border-green-500/20 transition-colors">
                      <div className="relative w-14 h-14 rounded-lg overflow-hidden bg-zinc-900 flex-shrink-0">
                        <Image src={o.image_url} alt={o.artwork_title} fill className="object-cover" unoptimized />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-bold text-amber-50 truncate">{o.artwork_title}</p>
                        <p className="text-xs text-gray-400">Buyer: <span className="text-gray-200">{o.buyer_name}</span></p>
                        <p className="text-xs text-gray-500 truncate">{o.shipping_address}</p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <p className="text-lg font-bold text-green-400">₹{Number(o.price).toLocaleString()}</p>
                        <p className="text-xs text-gray-600">{new Date(o.ordered_at).toLocaleDateString()}</p>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="border-t border-white/10 mt-4 pt-4 flex justify-between items-center text-sm">
                  <span className="text-gray-500">{orders.length} sale{orders.length !== 1 ? "s" : ""}</span>
                  <span className="text-green-400 font-bold">
                    Total: ₹{orders.reduce((sum, o) => sum + Number(o.price || 0), 0).toLocaleString()}
                  </span>
                </div>
              </>
            ) : (
              <p className="text-gray-500 text-sm">No sales yet. Your masterpieces are waiting for collectors!</p>
            )}
          </div>

          {/* Portfolio */}
          <div className="animate-fade-in" style={{ animationDelay: "200ms" }}>
            <h2 className="text-4xl md:text-5xl font-display mb-8 border-b border-amber-50/10 pb-4">
              My Portfolio
              {artworks.length > 0 && (
                <span className="text-lg text-gray-500 ml-4">{artworks.length} works</span>
              )}
            </h2>

            {artworks.length === 0 ? (
              <div className="text-center py-16">
                <div className="text-5xl mb-4 animate-float">🎨</div>
                <p className="text-gray-400 text-xl font-display">Your portfolio is currently empty.</p>
                <p className="text-gray-600 mt-2">Start uploading your masterpieces!</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                {artworks.map((item, idx) => (
                  <div
                    key={item.artwork_id}
                    className="group bg-zinc-900/50 border border-white/5 rounded-2xl overflow-hidden hover:border-amber-50/20 transition-all duration-500 animate-fade-in-up"
                    style={{ animationDelay: `${idx * 80}ms` }}
                  >
                    <div className="relative w-full h-56 bg-black">
                      <Image
                        src={item.image_url}
                        alt={item.title}
                        fill
                        className="object-contain"
                        unoptimized={true}
                      />
                    </div>
                    <div className="p-5">
                      <h3 className="text-xl font-display font-bold mb-1 truncate">{item.title}</h3>
                      <p className="text-gray-500 text-sm mb-3 line-clamp-2">{item.description}</p>
                      <div className="flex justify-between items-center border-t border-white/5 pt-3">
                        <span className="text-xl font-bold">₹{item.price}</span>
                        <span className="text-xs tracking-widest text-gray-500 uppercase px-3 py-1 bg-black rounded-full border border-white/10">
                          {categories.find((c) => c.category_id === item.category_id)?.name || "Art"}
                        </span>
                      </div>
                      <button
                        onClick={() => handleDeleteArtwork(item.artwork_id)}
                        disabled={deletingId === item.artwork_id}
                        className="w-full mt-3 py-2 bg-red-500/10 hover:bg-red-500 text-red-400 hover:text-white rounded-xl transition-all text-xs font-medium tracking-widest uppercase disabled:opacity-50"
                      >
                        {deletingId === item.artwork_id ? "Deleting..." : "Delete Artwork"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
