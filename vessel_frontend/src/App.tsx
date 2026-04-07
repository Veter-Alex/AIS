import { Route, Routes } from "react-router-dom";
import AiAssistantPage from "./pages/AiAssistantPage";
import VesselDetailPage from "./pages/VesselDetailPage";
import VesselListPage from "./pages/VesselListPage";

// Корневой компонент маршрутизации SPA.
//
// Единый стиль комментариев в проекте:
// 1) Сверху файла — контекст и архитектурная роль модуля.
// 2) Перед ключевыми блоками — объяснение "зачем", а не только "что".
// 3) Не дублируем очевидное поведение JSX/TS, комментируем решения.
function App() {
  return (
    <div className="min-h-screen bg-dark-bg text-gray-100">
      {/* Все маршруты приложения сконцентрированы в одном месте для предсказуемой навигации. */}
      <Routes>
        <Route path="/" element={<VesselListPage />} />
        <Route path="/ai" element={<AiAssistantPage />} />
        <Route path="/vessel/:imo" element={<VesselDetailPage />} />
      </Routes>
    </div>
  );
}

export default App;
