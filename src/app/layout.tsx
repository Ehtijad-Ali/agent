import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";
import { ThemeProvider } from "@/components/theme-provider";
import { SignalStoreProvider } from "@/components/store-provider";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Signal — Social Intent Radar",
  description:
    "Find people publicly asking for a product like yours, score how relevant each conversation is, and approve AI-drafted replies before posting. Human-approved, never autonomous.",
  keywords: [
    "social listening",
    "intent radar",
    "brand monitoring",
    "reply approval",
    "AI reply drafting",
  ],
  authors: [{ name: "Signal" }],
  icons: { icon: "/logo.svg" },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} antialiased`}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem
          disableTransitionOnChange
        >
          <SignalStoreProvider>{children}</SignalStoreProvider>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
