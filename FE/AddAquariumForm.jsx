import React, { useState } from "react";

function AddAquariumForm({ onAdded }) {
  const [formData, setFormData] = useState({
    user_id: "",
    name: "",
    size_litres: ""
  });

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const res = await fetch("http://localhost:8000/aquariums", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: parseInt(formData.user_id),
        name: formData.name,
        size_litres: parseFloat(formData.size_litres)
      })
    });
    if (res.ok) {
      const newAq = await res.json();
      onAdded(newAq);
      setFormData({ user_id: "", name: "", size_litres: "" });
    }
  };

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-3">
      <input
        name="user_id"
        placeholder="User ID"
        value={formData.user_id}
        onChange={handleChange}
        className="border p-2 w-full"
        required
      />
      <input
        name="name"
        placeholder="Nama Aquarium"
        value={formData.name}
        onChange={handleChange}
        className="border p-2 w-full"
        required
      />
      <input
        name="size_litres"
        placeholder="Ukuran (Liter)"
        value={formData.size_litres}
        onChange={handleChange}
        className="border p-2 w-full"
        required
      />
      <button type="submit" className="bg-blue-500 text-white p-2 rounded">
        Tambah Aquarium
      </button>
    </form>
  );
}

export default AddAquariumForm;
