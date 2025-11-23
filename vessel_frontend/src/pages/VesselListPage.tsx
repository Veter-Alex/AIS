import { useQuery } from '@tanstack/react-query';
import React, { useEffect, useState } from 'react';
import { vesselApi } from '../api/vesselApi';
import ExportButton from '../components/ExportButton';
import FilterPanel from '../components/FilterPanel';
import Pagination from '../components/Pagination';
import SearchBar from '../components/SearchBar';
import VesselCard from '../components/VesselCard';
import VesselTable from '../components/VesselTable';
import type { VesselFilters } from '../types/vessel';

const VesselListPage: React.FC = () => {
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');
  const [searchInput, setSearchInput] = useState('');
  const [filters, setFilters] = useState<VesselFilters>({
    page: 1,
    per_page: 20,
    sort_by: 'name',
    sort_order: 'asc',
    vessel_types: [],
    flags: [],
  });

  // Автоматический поиск при изменении ввода (с задержкой)
  useEffect(() => {
    const timer = setTimeout(() => {
      const trimmedSearch = searchInput.trim();
      setFilters(prev => ({ ...prev, search: trimmedSearch || undefined, page: 1 }));
    }, 500);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Загрузка статистики для фильтров
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: vesselApi.getStats,
  });

  // Загрузка судов
  const { data: vesselsData, isLoading, error } = useQuery({
    queryKey: ['vessels', filters],
    queryFn: () => vesselApi.getVessels(filters),
  });

  const handleSearch = () => {
    const trimmedSearch = searchInput.trim();
    setFilters({ ...filters, search: trimmedSearch || undefined, page: 1 });
  };

  const handleSort = (field: string) => {
    setFilters({
      ...filters,
      sort_by: field,
      sort_order: filters.sort_by === field && filters.sort_order === 'asc' ? 'desc' : 'asc',
    });
  };

  const totalPages = vesselsData ? Math.ceil(vesselsData.total / vesselsData.per_page) : 0;

  const vesselTypes = stats?.vessel_types.map(vt => vt.general_type) || [];
  const flags = stats?.flags.map(f => f.flag) || [];

  return (
    <div className="min-h-screen bg-dark-bg">
      {/* Header */}
      <header className="bg-dark-card border-b border-dark-border">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-3xl font-bold text-gray-100">База данных судов</h1>
            <div className="flex gap-4">
              <ExportButton filters={filters} />
            </div>
          </div>

          {/* Search */}
          <div className="mb-4">
            <SearchBar value={searchInput} onChange={setSearchInput} onSearch={handleSearch} />
          </div>

          {/* Stats */}
          {stats && (
            <div className="flex gap-4 text-sm text-gray-400">
              <span>Всего судов: {stats.total_vessels}</span>
              <span>•</span>
              <span>Типов: {stats.vessel_types.length}</span>
              <span>•</span>
              <span>Флагов: {stats.flags.length}</span>
            </div>
          )}
        </div>
      </header>

      <div className="container mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Filters */}
          <aside className="lg:col-span-1">
            <FilterPanel
              filters={filters}
              onFilterChange={(newFilters) => setFilters({ ...newFilters, page: 1 })}
              vesselTypes={vesselTypes}
              flags={flags}
            />
          </aside>

          {/* Main content */}
          <main className="lg:col-span-3">
            {/* View mode toggle */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex gap-2">
                <button
                  onClick={() => setViewMode('cards')}
                  className={`px-4 py-2 rounded transition-colors ${
                    viewMode === 'cards'
                      ? 'bg-blue-600 text-white'
                      : 'bg-dark-card text-gray-400 hover:bg-dark-hover'
                  }`}
                >
                  Карточки
                </button>
                <button
                  onClick={() => setViewMode('table')}
                  className={`px-4 py-2 rounded transition-colors ${
                    viewMode === 'table'
                      ? 'bg-blue-600 text-white'
                      : 'bg-dark-card text-gray-400 hover:bg-dark-hover'
                  }`}
                >
                  Таблица
                </button>
              </div>

              {vesselsData && (
                <span className="text-gray-400">
                  Показано {((vesselsData.page - 1) * vesselsData.per_page) + 1}-
                  {Math.min(vesselsData.page * vesselsData.per_page, vesselsData.total)} из {vesselsData.total}
                </span>
              )}
            </div>

            {/* Loading/Error states */}
            {isLoading && (
              <div className="text-center py-12 text-gray-400">Загрузка...</div>
            )}

            {error && (
              <div className="text-center py-12 text-red-400">
                Ошибка загрузки данных: {error instanceof Error ? error.message : 'Неизвестная ошибка'}
              </div>
            )}

            {/* Vessels display */}
            {vesselsData && vesselsData.vessels.length > 0 && (
              <>
                {viewMode === 'cards' ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {vesselsData.vessels.map((vessel) => (
                      <VesselCard key={vessel.id} vessel={vessel} />
                    ))}
                  </div>
                ) : (
                  <div className="bg-dark-card border border-dark-border rounded-lg overflow-hidden">
                    <VesselTable
                      vessels={vesselsData.vessels}
                      sortBy={filters.sort_by || 'name'}
                      sortOrder={filters.sort_order || 'asc'}
                      onSort={handleSort}
                    />
                  </div>
                )}

                <Pagination
                  currentPage={vesselsData.page}
                  totalPages={totalPages}
                  onPageChange={(page) => setFilters({ ...filters, page })}
                />
              </>
            )}

            {vesselsData && vesselsData.vessels.length === 0 && (
              <div className="text-center py-12 text-gray-400">
                Судна не найдены. Попробуйте изменить фильтры.
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
};

export default VesselListPage;
