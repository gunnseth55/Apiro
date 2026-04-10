import Link from "next/link";
import { FaInstagram, FaTwitter, FaPinterest, FaEnvelope } from "react-icons/fa";

export default function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer id="site-footer" className="bg-zinc-950 border-t border-white/5 text-gray-400">
      <div className="max-w-7xl mx-auto px-6 lg:px-12 py-16">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-12">
          {/* Brand */}
          <div className="md:col-span-1">
            <h3 className="text-2xl font-display font-bold text-amber-50 tracking-widest uppercase mb-4">
              Art Gallery
            </h3>
            <p className="text-sm leading-relaxed text-gray-500">
              A digital home for extraordinary art. Discover, collect, and support
              the world&apos;s most inspiring artists.
            </p>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="text-xs font-bold tracking-widest uppercase text-gray-300 mb-4">
              Explore
            </h4>
            <ul className="space-y-3">
              {[
                { href: "/", label: "Home" },
                { href: "/world", label: "Art Categories" },
                { href: "/vibes", label: "World Art" },
                { href: "/wishlist", label: "My Wishlist" },
              ].map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-sm hover:text-amber-50 transition-colors"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* For Artists */}
          <div>
            <h4 className="text-xs font-bold tracking-widest uppercase text-gray-300 mb-4">
              For Artists
            </h4>
            <ul className="space-y-3">
              {[
                { href: "/auth", label: "Artist Portal" },
                { href: "/dashboard", label: "My Studio" },
                { href: "/login", label: "Viewer Sign In" },
              ].map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-sm hover:text-amber-50 transition-colors"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Connect */}
          <div>
            <h4 className="text-xs font-bold tracking-widest uppercase text-gray-300 mb-4">
              Connect
            </h4>
            <div className="flex gap-4 mb-6">
              {[
                { icon: FaInstagram, label: "Instagram" },
                { icon: FaTwitter, label: "Twitter" },
                { icon: FaPinterest, label: "Pinterest" },
                { icon: FaEnvelope, label: "Email" },
              ].map((social) => (
                <button
                  key={social.label}
                  aria-label={social.label}
                  className="w-10 h-10 rounded-full border border-white/10 flex items-center justify-center text-gray-400 hover:text-amber-50 hover:border-amber-50/30 hover:bg-amber-50/5 transition-all"
                >
                  <social.icon className="text-lg" />
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-600">
              <FaEnvelope className="inline mr-2" />
              contact@artgallery.com
            </p>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="border-t border-white/5 mt-12 pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-xs text-gray-600">
            © {currentYear} Art Gallery. All rights reserved.
          </p>
          <div className="flex gap-6">
            <span className="text-xs text-gray-600 hover:text-gray-400 transition-colors cursor-pointer">
              Privacy Policy
            </span>
            <span className="text-xs text-gray-600 hover:text-gray-400 transition-colors cursor-pointer">
              Terms of Service
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
