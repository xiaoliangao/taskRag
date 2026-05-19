import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuthStore } from "../stores/authStore";

export default function RequireAdmin({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const location = useLocation();
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  if (!user.is_admin) return <Navigate to="/topics" replace />;
  return <>{children}</>;
}
