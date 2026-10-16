import type { Metadata } from "next";
import "./globals.css";
import "./brand.css";

export const metadata: Metadata = {
  title: "JanaМен — Digital HR",
  description: "Работа, развитие и забота о команде в одном пространстве.",
  robots: { index: false, follow: false },
  icons: { icon: "/brand/jana-digital.png", apple: "/brand/jana-digital.png" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body>{children}</body></html>;
}
