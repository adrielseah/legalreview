"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Search, Scale, Settings, LogOut } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useAuthContext } from "@/components/AuthProvider";

export function TopNav() {
  const [query, setQuery] = useState("");
  const router = useRouter();
  const { authUser, handleLogout } = useAuthContext();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      router.push(`/search?q=${encodeURIComponent(query.trim())}`);
    }
  };

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto flex h-14 max-w-7xl flex-wrap items-center gap-2 px-3 sm:gap-4 sm:px-4">
        {/* Logo */}
        <Link href="/vendors" className="flex shrink-0 items-center gap-2 font-semibold text-foreground">
          <Scale className="h-5 w-5 text-blue-400" />
          <span className="text-sm">ClauseLens</span>
        </Link>

        {/* Global search */}
        <form onSubmit={handleSearch} className="min-w-0 flex-1 sm:max-w-md">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <Input
              type="search"
              placeholder="Search…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="h-8 pl-8 text-xs bg-secondary/50 border-secondary"
              aria-label="Search clauses"
            />
          </div>
        </form>

        <nav className="ml-auto flex shrink-0 items-center gap-1">
          <Link
            href="/vendors"
            className="text-sm text-muted-foreground hover:text-foreground px-3 py-1 rounded-md hover:bg-accent transition-colors"
          >
            Vendors
          </Link>
          <Link
            href="/admin/precedents"
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground px-3 py-1 rounded-md hover:bg-accent transition-colors"
          >
            <Settings className="h-3.5 w-3.5" />
            Admin
          </Link>
          {authUser && (
            <button
              onClick={handleLogout}
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground px-3 py-1 rounded-md hover:bg-accent transition-colors"
              title={authUser.email}
            >
              <LogOut className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{authUser.name || authUser.email}</span>
            </button>
          )}
        </nav>
      </div>
    </header>
  );
}
