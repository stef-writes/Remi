import type { Metadata } from "next";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "REMI — Property Intelligence",
  description: "AI-powered property management analytics and operations.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-screen overflow-hidden bg-surface text-fg antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
