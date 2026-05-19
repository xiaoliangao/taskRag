import { useLocation } from "react-router-dom";

import type { ReactNode } from "react";

/**
 * Wrap routed content so each navigation re-keys the wrapper and replays the
 * fade-rise + stagger animation defined in globals.css.
 *
 * No animation library — just a key change on a CSS-animated div, which is
 * cheap and matches the rest of the design system (animations live in CSS).
 */
export default function PageTransition({ children }: { children: ReactNode }) {
  const location = useLocation();
  return (
    <div key={location.pathname} className="page-transition">
      {children}
    </div>
  );
}
