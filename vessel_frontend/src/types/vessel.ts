// Доменные типы фронтенда для сущности судна и связанных API-ответов.
// Все интерфейсы синхронизированы с backend-контрактом vessel_api.
export interface Vessel {
  id: number;
  name: string;
  imo: string;
  mmsi: string;
  call_sign: string;
  general_type: string;
  detailed_type: string;
  flag: string;
  year_built: number | null;
  length: number | null;
  width: number | null;
  dwt: number | null;
  gt: number | null;
  home_port: string | null;
  photo_path: string | null;
  description: string | null;
  info_source: string;
  updated_at: string | null;
}

// Ответ списка судов с пагинацией.
export interface VesselListResponse {
  total: number;
  page: number;
  per_page: number;
  vessels: Vessel[];
}

// Минимальная статистика, используемая в фильтрах и summary-блоке UI.
export interface StatsResponse {
  total_vessels: number;
  vessel_types: Array<{ general_type: string; count: number }>;
  flags: Array<{ flag: string; count: number }>;
}

// Параметры фильтрации и сортировки списка судов.
export interface VesselFilters {
  search?: string;
  vessel_types?: string[];
  flags?: string[];
  info_sources?: string[];
  year_from?: number;
  year_to?: number;
  sort_by?: string;
  sort_order?: "asc" | "desc";
  page?: number;
  per_page?: number;
}

// DTO для PATCH-обновления: поля опциональны, отправляются только измененные значения.
export interface VesselUpdate {
  name?: string;
  imo?: string;
  mmsi?: string;
  call_sign?: string;
  general_type?: string;
  detailed_type?: string;
  flag?: string;
  year_built?: number | null;
  length?: number | null;
  width?: number | null;
  dwt?: number | null;
  gt?: number | null;
  home_port?: string | null;
  description?: string | null;
}
