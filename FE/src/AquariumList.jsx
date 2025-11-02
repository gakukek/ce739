import React, { useEffect, useState } from "react";
import { fetchAquariums, deleteAquarium } from "./api";

export default function AquariumList() {
  const [aquariums, setAquariums] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    setLoading(true);
    const data = await fetchAquariums();
    setAquariums(data);
    setLoading(false);
  };

  const handleDelete = async (id) => {
    if (window.confirm("Yakin ingin menghapus data ini?")) {
      await deleteAquarium(id);
      loadData();
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) return <p>Loading data...</p>;

  return (
    <div>
      <h3>📦 Daftar Aquarium</h3>
      {aquariums.length === 0 ? (
        <p>Belum ada data aquarium.</p>
      ) : (
        <table border="1" cellPadding="8" style={{ width: "100%" }}>
          <thead style={{ backgroundColor: "#f0f0f0" }}>
            <tr>
              <th>ID</th>
              <th>Nama</th>
              <th>Volume (L)</th>
              <th>Feeding Time</th>
              <th>Aksi</th>
            </tr>
          </thead>
          <tbody>
            {aquariums.map((aq) => (
              <tr key={aq.id}>
                <td>{aq.id}</td>
                <td>{aq.name}</td>
                <td>{aq.volume}</td>
                <td>{aq.feeding_time || "-"}</td>
                <td>
                  <button
                    onClick={() => handleDelete(aq.id)}
                    style={{ backgroundColor: "red", color: "white" }}
                  >
                    Hapus
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
