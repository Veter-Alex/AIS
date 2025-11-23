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

export interface VesselListResponse {
  total: number;
  page: number;
  per_page: number;
  vessels: Vessel[];
}

export interface StatsResponse {
  total_vessels: number;
  vessel_types: Array<{ general_type: string; count: number }>;
  flags: Array<{ flag: string; count: number }>;
}

export interface VesselFilters {
  search?: string;
  vessel_types?: string[];
  flags?: string[];
  year_from?: number;
  year_to?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  page?: number;
  per_page?: number;
}

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
