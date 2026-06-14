import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import "./globals.css";

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "ShortsGen AI | Premium Talking Head & Viral Reels Builder",
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
    <html lang="en" className={`${outfit.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col" suppressHydrationWarning>{children}</body>
    </html>
  );
}
