"use client";
import Link from "next/link";
import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { FiMenu, FiX } from "react-icons/fi";

export default function Header() {
  const pathname = usePathname();
  const [artistId, setArtistId] = useState(null);
  const [viewerId, setViewerId] = useState(null);
  const [viewerName, setViewerName] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const syncFromStorage = () => {
    const aId = localStorage.getItem("artist_id");
    const vId = localStorage.getItem("viewer_id");
    const vName = localStorage.getItem("viewer_name");
    setArtistId(aId);
    setViewerId(vId);
    setViewerName(vName || "");
    setIsAdmin(localStorage.getItem("is_admin") === "true");
    setMounted(true);
  };

  // Re-sync from localStorage on every route change
  useEffect(() => {
    syncFromStorage();
  }, [pathname]);

  useEffect(() => {
    window.addEventListener("storage", syncFromStorage);
    return () => window.removeEventListener("storage", syncFromStorage);
  }, []);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleViewerLogout = () => {
    localStorage.removeItem("viewer_id");
    localStorage.removeItem("viewer_name");
    localStorage.removeItem("is_admin");
    setViewerId(null);
    setViewerName("");
    setIsAdmin(false);
    window.location.href = "/";
  };

  const handleArtistLogout = () => {
    localStorage.removeItem("artist_id");
    localStorage.removeItem("artist_name");
    setArtistId(null);
    window.location.href = "/";
  };

  const closeMobile = () => setMobileOpen(false);

  const navLinks = [
    { href: "/", label: "Home" },
    { href: "/world", label: "Explore" },
    { href: "/vibes", label: "World Art" },
    { href: "/wishlist", label: "Wishlist" },
  ];

  return (
    <header
      id="main-header"
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${scrolled
        ? "bg-black/80 backdrop-blur-xl border-b border-white/5 shadow-lg shadow-black/20"
        : "bg-transparent"
        }`}
    >
      <div className="max-w-7xl mx-auto px-6 lg:px-12 py-4 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 group" onClick={closeMobile}>
          <span className="text-xl font-display font-bold text-amber-50 tracking-widest uppercase group-hover:text-amber-400 transition-colors">
            Art Gallery
          </span>
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden md:flex items-center gap-8">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-sm text-gray-300 hover:text-amber-50 transition-colors tracking-widest uppercase font-medium"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        {/* Desktop Auth */}
        <div className="hidden md:flex items-center gap-4">
          {mounted && (
            <>
              {viewerId ? (
                <div className="flex items-center gap-3">
                  {isAdmin && (
                    <Link
                      href="/admin"
                      className="text-red-400/80 hover:text-red-400 transition-colors text-xs uppercase tracking-widest font-bold border border-red-500/30 px-3 py-1.5 rounded-full hover:bg-red-500/10"
                    >
                      Admin
                    </Link>
                  )}
                  <span className="text-gray-400 text-sm tracking-wider">
                    Hi, {viewerName}
                  </span>
                  <button
                    onClick={handleViewerLogout}
                    className="text-red-500/80 hover:text-red-400 transition-colors text-xs uppercase tracking-widest"
                  >
                    [Logout]
                  </button>
                </div>
              ) : artistId ? (
                <div className="flex items-center gap-3">
                  <Link
                    href="/dashboard"
                    className="text-amber-50 border border-amber-50/40 px-5 py-2 rounded-xl hover:bg-amber-50 hover:text-black transition-all font-display text-sm uppercase tracking-widest"
                  >
                    My Studio
                  </Link>
                  <button
                    onClick={handleArtistLogout}
                    className="text-red-500/80 hover:text-red-400 transition-colors text-xs uppercase tracking-widest"
                  >
                    [Logout]
                  </button>
                </div>
              ) : (
                <>
                  <Link
                    href="/login"
                    className="text-amber-50 hover:text-white transition-colors text-sm uppercase tracking-widest"
                  >
                    Sign In
                  </Link>
                  <Link
                    href="/auth"
                    className="text-amber-50/70 hover:text-amber-50 transition-colors text-sm uppercase tracking-widest"
                  >
                    Artist Portal
                  </Link>
                </>
              )}
            </>
          )}
        </div>

        {/* Mobile Hamburger */}
        <button
          id="mobile-menu-toggle"
          onClick={() => setMobileOpen(!mobileOpen)}
          className="md:hidden text-white text-2xl p-2 hover:bg-white/10 rounded-lg transition-colors"
          aria-label="Toggle navigation menu"
        >
          {mobileOpen ? <FiX /> : <FiMenu />}
        </button>
      </div>

      {/* Mobile Drawer */}
      <div
        className={`md:hidden fixed inset-0 top-[72px] z-40 transition-all duration-500 ${mobileOpen
          ? "opacity-100 pointer-events-auto"
          : "opacity-0 pointer-events-none"
          }`}
      >
        {/* Backdrop */}
        <div
          className="absolute inset-0 bg-black/60 backdrop-blur-sm"
          onClick={closeMobile}
        />

        {/* Drawer Content */}
        <nav
          className={`relative bg-black/95 border-t border-white/5 p-6 space-y-2 transition-transform duration-500 ${mobileOpen ? "translate-y-0" : "-translate-y-4"
            }`}
        >
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={closeMobile}
              className="block py-3 px-4 text-lg text-gray-200 hover:text-amber-50 hover:bg-white/5 rounded-xl transition-colors font-display tracking-wider"
            >
              {link.label}
            </Link>
          ))}

          <div className="border-t border-white/10 pt-4 mt-4 space-y-2">
            {mounted && (
              <>
                {viewerId ? (
                  <>
                    <p className="text-gray-400 text-sm px-4 tracking-wider">
                      Signed in as <span className="text-white">{viewerName}</span>
                    </p>
                    {isAdmin && (
                      <Link
                        href="/admin"
                        onClick={closeMobile}
                        className="block py-3 px-4 text-red-400 hover:bg-red-500/10 rounded-xl transition-colors text-sm uppercase tracking-widest font-bold"
                      >
                        Admin Panel
                      </Link>
                    )}
                    <button
                      onClick={() => {
                        handleViewerLogout();
                        closeMobile();
                      }}
                      className="block w-full text-left py-3 px-4 text-red-400 hover:bg-red-500/10 rounded-xl transition-colors text-sm uppercase tracking-widest"
                    >
                      Logout
                    </button>
                  </>
                ) : artistId ? (
                  <>
                    <p className="text-gray-400 text-sm px-4 tracking-wider">
                      Signed in as <span className="text-white">Artist</span>
                    </p>
                    <Link
                      href="/dashboard"
                      onClick={closeMobile}
                      className="block py-3 px-4 text-amber-50 border border-amber-50/30 hover:bg-amber-50 hover:text-black rounded-xl transition-all text-center font-display tracking-widest uppercase"
                    >
                      My Studio
                    </Link>
                    <button
                      onClick={() => {
                        handleArtistLogout();
                        closeMobile();
                      }}
                      className="block w-full text-left py-3 px-4 text-red-400 hover:bg-red-500/10 rounded-xl transition-colors text-sm uppercase tracking-widest"
                    >
                      Logout
                    </button>
                  </>
                ) : (
                  <>
                    <Link
                      href="/login"
                      onClick={closeMobile}
                      className="block py-3 px-4 text-amber-50 bg-amber-50/10 hover:bg-amber-50/20 rounded-xl transition-colors text-center font-display tracking-widest uppercase"
                    >
                      Sign In
                    </Link>
                    <Link
                      href="/auth"
                      onClick={closeMobile}
                      className="block py-3 px-4 text-amber-50/70 hover:text-amber-50 hover:bg-white/5 rounded-xl transition-colors text-center font-display tracking-widest uppercase"
                    >
                      Artist Portal
                    </Link>
                  </>
                )}
              </>
            )}
          </div>
        </nav>
      </div>
    </header>
  );
}