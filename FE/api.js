import axios from "axios";

// 🔗 Ambil URL backend dari environment variable (file .env di folder FE)
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

// 🔹 GET - ambil semua aquarium
export const fetchAquariums = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/aquariums`);
    return res.data;
  } catch (error) {
    console.error("Gagal mengambil data aquarium:", error);
    return [];
  }
};

// 🔹 POST - tambah aquarium baru
export const addAquarium = async (aquariumData) => {
  try {
    const res = await axios.post(`${API_BASE_URL}/aquariums`, aquariumData);
    return res.data;
  } catch (error) {
    console.error("Gagal menambahkan aquarium:", error);
    throw error;
  }
};

// 🔹 DELETE - hapus aquarium (opsional)
export const deleteAquarium = async (id) => {
  try {
    await axios.delete(`${API_BASE_URL}/aquariums/${id}`);
  } catch (error) {
    console.error("Gagal menghapus aquarium:", error);
  }
};
