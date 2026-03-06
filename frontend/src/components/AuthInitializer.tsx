"use client";

import { useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";

export default function AuthInitializer() {
  const initialize = useAuth((s) => s.initialize);
  useEffect(() => {
    initialize();
  }, [initialize]);
  return null;
}
