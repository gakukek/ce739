import React, { useState } from "react";
import { addAquarium } from "./api";

export default function AddAquariumForm({ onAdded }) {
  const [name, setName] = useState("");
  const [volume, setVolume] = useState("");
  const [feedingTime, setFeedingTime] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name || !volume) {
      alert("Lengkapi semua field!");
      return;
    }

    await addAquarium({
      name,
      volume: parseFloat(volume),
      feeding_time: feedingTime,
    });

    alert("✅ Data aquarium berhasil ditambahkan!");
    setName("");
    setVolume("");
    setFeedingTime("");
    onAdded();
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        border: "1px solid #ccc",
        padding: "20px",
        borderRadius: "10px",
        marginBottom: "30px",
      }}
    >
      <h3>➕ Tambah Aquarium</h3>

      <div style={{ marginBottom: "10px" }}>
        <label>Nama Aquarium:</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          style={{ marginLeft: "10px" }}
        />
      </div>

      <div style={{ marginBottom: "10px" }}>
        <label>Volume (liter):</label>
        <input
          type="number"
          value={volume}
          onChange={(e) => setVolume(e.target.value)}
          required
          style={{ marginLeft: "10px" }}
        />
      </div>

      <div style={{ marginBottom: "10px" }}>
        <label>Waktu Pemberian Pakan:</label>
        <input
          type="time"
          value={feedingTime}
          onChange={(e) => setFeedingTime(e.target.value)}
          style={{ marginLeft: "10px" }}
        />
      </div>

      <button type="submit" style={{ padding: "8px 16px" }}>
        Simpan
      </button>
    </form>
  );
}
