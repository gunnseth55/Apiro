import type { Metadata } from "next";
import "./globals.css";
import Header from "./(components)/layouts/Header.jsx";
import Footer from "./(components)/layouts/Footer.jsx";

export const metadata: Metadata = {
  title: "Art Gallery | Discover & Collect Extraordinary Art",
  description:
    "A digital gallery to discover, collect, and support the world's most inspiring artists. Browse artworks, explore global art heritage, and connect with creators.",
  keywords: "art gallery, artworks, artists, paintings, sculptures, digital art, art collection",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link
          rel="preconnect"
          href="https://fonts.googleapis.com"
        />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-black text-white antialiased">
        <Header />
        <main className="min-h-screen">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
