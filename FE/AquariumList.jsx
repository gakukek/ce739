import React, { useEffect, useState } from "react";

const API_BASE = "https://aquascape.onrender.com";

function AquariumList() {
  const [aquariums, setAquariums] = useState([]);

  async function fetchAquariums() {
    try {
      const res = await fetch(`${API_BASE}/aquariums`);
      const data = await res.json();
      // INI MASIH AQUARIUM USER ID 1
      setAquariums(Array.isArray(data) ? data.filter(a => a.user_id === 1) : []);
    } catch (err) {
      console.error("Failed to fetch aquariums", err);
    }
  }

  useEffect(() => {
    fetchAquariums();
  }, []);

  return (
    <div className="p-4">
      <h2 className="text-xl font-bold mb-2">Daftar Aquarium</h2>
      <ul className="space-y-2">
        {aquariums.map((aq) => (
          <li key={aq.id} className="border rounded p-2">
            <p><strong>{aq.name}</strong> — {aq.size_litres ?? 0} L</p>
            <p className="text-sm text-gray-500">User ID: {aq.user_id}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default AquariumList;
