import axios from "axios";

const client = axios.create({ baseURL: "", timeout: 60000 });

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("kb_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401 && !location.hash.includes("login")) {
      localStorage.removeItem("kb_token");
      location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default client;
