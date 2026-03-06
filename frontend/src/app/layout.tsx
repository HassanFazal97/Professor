import type { Metadata } from "next";
import "./globals.css";
import AuthInitializer from "@/components/AuthInitializer";
import GoogleProviderWrapper from "@/components/GoogleProviderWrapper";

export const metadata: Metadata = {
  title: "AI Tutor — Professor KIA",
  description: "Voice-first AI tutoring with an interactive whiteboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="h-screen overflow-hidden bg-gray-50">
        <GoogleProviderWrapper>
          <AuthInitializer />
          {children}
        </GoogleProviderWrapper>
      </body>
    </html>
  );
}
