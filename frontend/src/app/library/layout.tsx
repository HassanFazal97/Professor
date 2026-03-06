"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

export default function LibraryLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, logout } = useAuth();

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <div className="flex h-screen flex-col bg-gray-50">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-indigo-600">Professor KIA</span>
          <span className="text-sm text-gray-400">Your notebooks</span>
        </div>
        <div className="flex items-center gap-3">
          {user?.avatar_url && (
            <img
              src={user.avatar_url}
              alt={user.display_name ?? ""}
              className="h-8 w-8 rounded-full object-cover"
            />
          )}
          <span className="text-sm text-gray-700">
            {user?.display_name ?? user?.email}
          </span>
          <button
            onClick={handleLogout}
            className="rounded-md px-3 py-1.5 text-xs font-medium text-gray-500 hover:bg-gray-100"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
