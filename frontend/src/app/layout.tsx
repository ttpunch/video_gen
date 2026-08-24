import type { Metadata } from "next";
import { Familjen_Grotesk, Schibsted_Grotesk } from "next/font/google";
import "./globals.css";

// Studio Noir type system: a characterful grotesk display + a refined grotesk body.
const display = Familjen_Grotesk({
  variable: "--font-display-src",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const body = Schibsted_Grotesk({
  variable: "--font-body-src",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "ShortsGen AI | Viral Shorts & Reels Builder",
  description: "Create stunning viral vertical shorts and talking head videos from text automatically. Built with Next.js, FastAPI, Kokoro ONNX, Leonardo.ai & Wav2Lip.",
  keywords: ["video generator", "AI shorts", "viral reels", "talking head AI", "Wav2Lip", "Kokoro ONNX", "Leonardo AI"],
  authors: [{ name: "ShortsGen AI Team" }],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col" suppressHydrationWarning>{children}</body>
    </html>
  );
}
