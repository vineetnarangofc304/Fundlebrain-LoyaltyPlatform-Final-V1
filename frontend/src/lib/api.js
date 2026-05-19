import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_URL = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API_URL,
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("kazo_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401 && !window.location.pathname.startsWith("/login")) {
      localStorage.removeItem("kazo_token");
      localStorage.removeItem("kazo_user");
      const portal = localStorage.getItem("kazo_portal") || "enterprise";
      window.location.href = portal === "store" ? "/store/login" : portal === "crm" ? "/crm/login" : "/enterprise/login";
    }
    return Promise.reject(err);
  }
);

export default api;
