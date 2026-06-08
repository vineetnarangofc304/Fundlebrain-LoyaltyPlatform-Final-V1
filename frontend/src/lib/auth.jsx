import React, { createContext, useContext, useEffect, useState } from "react";
import api from "./api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("kazo_token");
    const cached = localStorage.getItem("kazo_user");
    if (token && cached) {
      try {
        setUser(JSON.parse(cached));
      } catch (e) { /* ignore bad cache */ }
      // refresh in background
      api.get("/auth/me").then((r) => {
        setUser(r.data);
        localStorage.setItem("kazo_user", JSON.stringify(r.data));
      }).catch(() => {});
    }
    setLoading(false);
  }, []);

  const login = async (email, password, portal = "enterprise") => {
    const r = await api.post("/auth/login", { email, password, portal });
    localStorage.setItem("kazo_token", r.data.token);
    localStorage.setItem("kazo_user", JSON.stringify(r.data.user));
    localStorage.setItem("kazo_portal", portal);
    setUser(r.data.user);
    return r.data.user;
  };

  // Apply a session obtained outside the email/password flow (e.g. the read-only
  // demo session used by the public guided tour at /demo).
  const applySession = (token, sessionUser, portal = "crm") => {
    localStorage.setItem("kazo_token", token);
    localStorage.setItem("kazo_user", JSON.stringify(sessionUser));
    localStorage.setItem("kazo_portal", portal);
    setUser(sessionUser);
    return sessionUser;
  };

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (e) { /* ignore */ }
    localStorage.removeItem("kazo_token");
    localStorage.removeItem("kazo_user");
    setUser(null);
  };

  return (
    <AuthCtx.Provider value={{ user, loading, login, applySession, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);

export function hasRole(user, ...roles) {
  if (!user) return false;
  return roles.includes(user.role);
}
