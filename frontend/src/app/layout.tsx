import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "REMI — Property Intelligence",
  description: "AI-powered property management analytics and operations.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="h-screen overflow-hidden bg-zinc-950 text-zinc-100 antialiased">
        {children}
      </body>
    </html>
  );
}
