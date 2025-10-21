import React, { useState } from "react";
import AddAquariumForm from "./AddAquariumForm";
import AquariumList from "./AquariumList";

export default function App() {
  const [refresh, setRefresh] = useState(false);

  const reloadList = () => setRefresh(!refresh);

  return (
    <div style={{ padding: "2rem", fontFamily: "Arial" }}>
      <h1>🐠 Smart Aquarium Feeder Dashboard</h1>
      <AddAquariumForm onAdded={reloadList} />
      <AquariumList key={refresh} />
    </div>
  );
}
