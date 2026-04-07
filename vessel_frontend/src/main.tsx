import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

// Глобальный клиент React Query.
//
// Принятые параметры:
// - refetchOnWindowFocus=false: не дергаем API при каждом фокусе окна;
// - retry=1: один повтор при временной сетевой ошибке,
//   чтобы не маскировать постоянные проблемы бекенда.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// Точка монтирования приложения.
// Порядок провайдеров важен:
// 1) QueryClientProvider поднимает слой работы с данными;
// 2) BrowserRouter включает маршрутизацию;
// 3) App рендерит экранные страницы.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
