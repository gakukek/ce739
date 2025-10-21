import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export const fetchAquariums = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/aquariums`);
    return res.data;
  } catch (error) {
    console.error("Gagal mengambil data:", error);
    return [];
  }
};

export const addAquarium = async (data) => {
  try {
    const res = await axios.post(`${API_BASE_URL}/aquariums`, data);
    return res.data;
  } catch (error) {
    console.error("Gagal menambahkan data:", error);
  }
};

export const deleteAquarium = async (id) => {
  try {
    await axios.delete(`${API_BASE_URL}/aquariums/${id}`);
  } catch (error) {
    console.error("Gagal menghapus data:", error);
  }
};
