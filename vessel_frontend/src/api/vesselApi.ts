import axios from 'axios';
import type { StatsResponse, Vessel, VesselFilters, VesselListResponse, VesselUpdate } from '../types/vessel';

// Пустой базовый URL - используем относительные пути через nginx proxy
const API_BASE_URL = '';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const vesselApi = {
  getVessels: async (filters: VesselFilters): Promise<VesselListResponse> => {
    const params = new URLSearchParams();
    
    if (filters.search) params.append('search', filters.search);
    if (filters.vessel_types?.length) params.append('vessel_types', filters.vessel_types.join(','));
    if (filters.flags?.length) params.append('flags', filters.flags.join(','));
    if (filters.year_from) params.append('year_from', filters.year_from.toString());
    if (filters.year_to) params.append('year_to', filters.year_to.toString());
    if (filters.sort_by) params.append('sort_by', filters.sort_by);
    if (filters.sort_order) params.append('sort_order', filters.sort_order);
    if (filters.page) params.append('page', filters.page.toString());
    if (filters.per_page) params.append('per_page', filters.per_page.toString());

    const response = await api.get<VesselListResponse>('/vessels/', { params });
    return response.data;
  },

  getVesselByImo: async (imo: string): Promise<Vessel> => {
    const response = await api.get<Vessel>(`/vessels/${imo}`);
    return response.data;
  },

  updateVessel: async (imo: string, data: VesselUpdate): Promise<Vessel> => {
    const response = await api.patch<Vessel>(`/vessels/${imo}`, data);
    return response.data;
  },

  getStats: async (): Promise<StatsResponse> => {
    const response = await api.get<StatsResponse>('/vessels/stats/summary');
    return response.data;
  },

  exportVessels: (format: 'csv' | 'json', filters: VesselFilters): string => {
    const params = new URLSearchParams();
    
    if (filters.search) params.append('search', filters.search);
    if (filters.vessel_types?.length) params.append('vessel_types', filters.vessel_types.join(','));
    if (filters.flags?.length) params.append('flags', filters.flags.join(','));
    if (filters.year_from) params.append('year_from', filters.year_from.toString());
    if (filters.year_to) params.append('year_to', filters.year_to.toString());

    return `${API_BASE_URL}/vessels/export/${format}?${params.toString()}`;
  },

  getImageUrl: (photoPath: string | null): string | null => {
    if (!photoPath) return null;
    const filename = photoPath.split('/').pop();
    return `${API_BASE_URL}/images/${filename}`;
  },
};
