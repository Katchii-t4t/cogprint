import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Paste from "./pages/Paste";
import Plan from "./pages/Plan";
import Cards from "./pages/Cards";
import Grow from "./pages/Grow";
import Checks from "./pages/Checks";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Paste />} />
        <Route path="/plan" element={<Plan />} />
        <Route path="/cards" element={<Cards />} />
        <Route path="/grow" element={<Grow />} />
        <Route path="/checks" element={<Checks />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
