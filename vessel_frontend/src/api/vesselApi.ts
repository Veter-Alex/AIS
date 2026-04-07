import axios from "axios";
import type {
  StatsResponse,
  Vessel,
  VesselFilters,
  VesselListResponse,
  VesselUpdate,
} from "../types/vessel";

// API-клиент для CRUD/поисковых операций по судам.
//
// Важно: используем относительные пути.
// Это позволяет проксировать запросы через nginx в docker-compose,
// не открывая CORS между origin'ами фронтенда и backend-сервисов.
const API_BASE_URL = "";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

export const vesselApi = {
  // Получить пагинированный список судов по текущим фильтрам.
  // Преобразуем объект фильтров в query-параметры так,
  // чтобы backend получал стабильный и явный контракт.
  getVessels: async (filters: VesselFilters): Promise<VesselListResponse> => {
    const params = new URLSearchParams();

    if (filters.search) params.append("search", filters.search);
    if (filters.vessel_types?.length)
      params.append("vessel_types", filters.vessel_types.join(","));
    if (filters.flags?.length) params.append("flags", filters.flags.join(","));
    if (filters.info_sources?.length)
      params.append("info_sources", filters.info_sources.join(","));
    if (filters.year_from)
      params.append("year_from", filters.year_from.toString());
    if (filters.year_to) params.append("year_to", filters.year_to.toString());
    if (filters.sort_by) params.append("sort_by", filters.sort_by);
    if (filters.sort_order) params.append("sort_order", filters.sort_order);
    if (filters.page) params.append("page", filters.page.toString());
    if (filters.per_page)
      params.append("per_page", filters.per_page.toString());

    const response = await api.get<VesselListResponse>("/vessels/", { params });
    return response.data;
  },

  // Детальная карточка судна по IMO.
  getVesselByImo: async (imo: string): Promise<Vessel> => {
    const response = await api.get<Vessel>(`/vessels/${imo}`);
    return response.data;
  },

  // Частичное обновление карточки судна.
  // На клиенте отправляются только реально измененные поля.
  updateVessel: async (imo: string, data: VesselUpdate): Promise<Vessel> => {
    const response = await api.patch<Vessel>(`/vessels/${imo}`, data);
    return response.data;
  },

  // Агрегированная статистика для панели фильтров.
  getStats: async (): Promise<StatsResponse> => {
    const response = await api.get<StatsResponse>("/vessels/stats/summary");
    return response.data;
  },

  // Источники данных (например, marinetraffic, myshiptracking) с количеством записей.
  getSources: async (): Promise<{
    sources: Array<{ info_source: string; count: number }>;
  }> => {
    const response = await api.get("/vessels/stats/sources");
    return response.data;
  },

  // Генерация URL экспорта с учетом тех же фильтров, что применены в UI.
  // Возвращаем строку URL, чтобы браузер мог инициировать загрузку файла напрямую.
  exportVessels: (format: "csv" | "json", filters: VesselFilters): string => {
    const params = new URLSearchParams();

    if (filters.search) params.append("search", filters.search);
    if (filters.vessel_types?.length)
      params.append("vessel_types", filters.vessel_types.join(","));
    if (filters.flags?.length) params.append("flags", filters.flags.join(","));
    if (filters.info_sources?.length)
      params.append("info_sources", filters.info_sources.join(","));
    if (filters.year_from)
      params.append("year_from", filters.year_from.toString());
    if (filters.year_to) params.append("year_to", filters.year_to.toString());

    return `${API_BASE_URL}/vessels/export/${format}?${params.toString()}`;
  },

  // Нормализуем относительный путь изображения в URL, пригодный для браузера.
  getImageUrl: (photoPath: string | null): string | null => {
    if (!photoPath) return null;
    const filename = photoPath.split("/").pop();
    return `${API_BASE_URL}/images/${filename}`;
  },
};
