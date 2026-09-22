import { callLogoutHandler } from "@/lib/auth";
import { showThrottledErrorToast } from "@/lib/error";
import axios from "axios";
import { SessionService } from "./session";

const baseURL = import.meta.env.DEV ? "http://localhost:8000/api/" : "/api/";

const axiosInstance = axios.create({
  baseURL: baseURL,
  timeout: 500000,
  headers: {
    "Content-Type": "application/json",
    accept: "application/json",
  },
});

axiosInstance.interceptors.request.use(
  (config) => {
    const token = SessionService.getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (
      error.response &&
      error.response.status === 401 &&
      SessionService.getRefreshToken() &&
      originalRequest.headers["retry"] != 1
    ) {
      try {
        const res = await axiosInstance({
          url: "users/token/refresh/",
          method: "post",
          data: { refresh: SessionService.getRefreshToken() },
          headers: { retry: 1 },
        });

        if (res.status === 200) {
          SessionService.setAccessToken(res.data.access);
          SessionService.setRefreshToken(res.data.refresh);
          axiosInstance.defaults.headers.Authorization = `Bearer ${SessionService.getAccessToken()}`;
          originalRequest.headers.Authorization = `Bearer ${SessionService.getAccessToken()}`;
          originalRequest.headers["retry"] = 1;
          return axiosInstance(originalRequest);
        }
      } catch (refreshError) {
        callLogoutHandler();
        return Promise.reject(refreshError);
      }
    } else if (originalRequest.headers["retry"] >= 1) {
      callLogoutHandler();
    } else {
      const status = error.response?.status;
      const detail =
        error.response?.data?.detail ||
        error.response?.data?.error ||
        error.response?.data?.message;
      const message = detail || `Request failed (${status || "Network error"})`;
      showThrottledErrorToast(originalRequest?.url || "unknown", message);
    }

    return Promise.reject(error);
  }
);

export default axiosInstance;
