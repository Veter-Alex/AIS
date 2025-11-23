import { Route, Routes } from 'react-router-dom';
import VesselDetailPage from './pages/VesselDetailPage';
import VesselListPage from './pages/VesselListPage';

function App() {
  return (
    <div className="min-h-screen bg-dark-bg text-gray-100">
      <Routes>
        <Route path="/" element={<VesselListPage />} />
        <Route path="/vessel/:imo" element={<VesselDetailPage />} />
      </Routes>
    </div>
  );
}

export default App;
