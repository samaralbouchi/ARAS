import axios from "axios";

const api = axios.create({
  baseURL: "https://aras-enab.onrender.com",
});

export default api;