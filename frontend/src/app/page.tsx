"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

export default function RootPage() {
  const router = useRouter();
  const isAuthenticated = useAuth((s) => s.isAuthenticated);

  useEffect(() => {
    if (isAuthenticated) {
      router.replace("/library");
    } else {
      router.replace("/login");
    }
  }, [isAuthenticated, router]);

  return null;
}
