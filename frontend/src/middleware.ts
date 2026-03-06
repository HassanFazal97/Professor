import { NextRequest, NextResponse } from "next/server";

const PROTECTED = ["/library", "/notebook"];
const AUTH_PAGES = ["/login"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const token = req.cookies.get("professor_token")?.value;

  const isProtected = PROTECTED.some((p) => pathname.startsWith(p));
  const isAuthPage = AUTH_PAGES.some((p) => pathname.startsWith(p));

  if (isProtected && !token) {
    return NextResponse.redirect(new URL("/login", req.url));
  }

  if (isAuthPage && token) {
    return NextResponse.redirect(new URL("/library", req.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/library/:path*", "/notebook/:path*", "/login"],
};
