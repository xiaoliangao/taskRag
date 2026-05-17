import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuthStore } from "../stores/authStore";

export default function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.accessToken);
  const location = useLocation();
  if (!token) return <Navigate to="/login" state={{ from: location }} replace />;
  return <>{children}</>;
}
