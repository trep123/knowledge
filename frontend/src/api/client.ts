import axios from "axios";
import { useAuth } from "../store/auth";

const client = axios.create({ baseURL: "", timeout: 60000 });

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("kb_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    // 登录接口本身的 401 是“用户名或密码错误”，交给页面提示，不能跳转刷新
    const isLoginRequest = (error.config?.url || "").includes("/auth/login");
    if (error.response?.status === 401 && !isLoginRequest && location.pathname !== "/login") {
      useAuth.getState().logout();
      location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default client;
