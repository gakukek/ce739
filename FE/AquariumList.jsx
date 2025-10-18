import React, { useEffect, useState } from "react";

function AquariumList() {
  const [aquariums, setAquariums] = useState([]);

  useEffect(() => {
    fetch("http://localhost:8000/aquariums")
      .then((res) => res.json())
      .then((data) => setAquariums(data))
      .catch((err) => console.error("Fetch error:", err));
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
