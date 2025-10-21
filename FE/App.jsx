import React, { useState } from "react";
import AquariumList from "./components/AquariumList";
import AddAquariumForm from "./components/AddAquariumForm";

function App() {
  const [updateTrigger, setUpdateTrigger] = useState(0);

  const handleAdded = () => {
    setUpdateTrigger((prev) => prev + 1); // memicu refresh list
  };

  return (
    <div className="max-w-lg mx-auto mt-8">
      <AddAquariumForm onAdded={handleAdded} />
      <AquariumList key={updateTrigger} />
    </div>
  );
}

export default App;
