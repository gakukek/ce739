import React, { useState } from "react";


function AddAquariumForm({ onAdded }) {
  const [formData, setFormData] = useState({
    user_id: "",
    name: "",
    size_litres: "",
    feeding_volume_grams: "",
    feeding_period_hours: ""
  });

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const payload = {
      user_id: formData.user_id,
      name: formData.name,
      size_litres: parseFloat(formData.size_litres) || 0,
      feeding_volume_grams: parseFloat(formData.feeding_volume_grams) || 2.0,
      feeding_period_hours: parseFloat(formData.feeding_period_hours) || 12
    };
    const res = await fetch("http://localhost:8000/aquariums", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      const newAq = await res.json();
      onAdded(newAq);
      setFormData({ name: "", size_litres: "" });
    } else {
      const txt = await res.text().catch(() => res.statusText);
      console.error("Add aquarium failed:", txt);
      alert("Failed to add aquarium: " + txt);
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
      <input
        name="feeding_volume_grams"
        placeholder="Jumlah Makanan dalam Gram"
        value={formData.feeding_volume_grams}
        onChange={handleChange}
        className="border p-2 w-full"
        required
      />
      <input
        name="feeding_period_hours"
        placeholder="Periode Pemberian Makanan (Jam)"
        value={formData.feeding_period_hours}
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
