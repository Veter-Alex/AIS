import React, { useState } from "react";
import type { VesselFilters } from "../types/vessel";

interface FilterPanelProps {
  filters: VesselFilters;
  onFilterChange: (filters: VesselFilters) => void;
  vesselTypes: string[];
  flags: string[];
  sources: string[];
}

// Боковая панель фильтров списка судов.
//
// Принцип: все фильтры контролируются родителем через единый объект `filters`,
// а компонент отвечает только за UI и генерацию нового состояния.
const FilterPanel: React.FC<FilterPanelProps> = ({
  filters,
  onFilterChange,
  vesselTypes,
  flags,
  sources,
}) => {
  // Сворачивание панели полезно на узких экранах и при большом числе опций.
  const [isExpanded, setIsExpanded] = useState(false);

  // Мультивыбор типов: повторный клик по элементу снимает фильтр.
  const handleTypeChange = (type: string) => {
    const currentTypes = filters.vessel_types || [];
    const newTypes = currentTypes.includes(type)
      ? currentTypes.filter((t) => t !== type)
      : [...currentTypes, type];
    onFilterChange({ ...filters, vessel_types: newTypes });
  };

  // Мультивыбор флагов по той же схеме toggle.
  const handleFlagChange = (flag: string) => {
    const currentFlags = filters.flags || [];
    const newFlags = currentFlags.includes(flag)
      ? currentFlags.filter((f) => f !== flag)
      : [...currentFlags, flag];
    onFilterChange({ ...filters, flags: newFlags });
  };

  // Мультивыбор источников данных.
  const handleSourceChange = (source: string) => {
    const currentSources = filters.info_sources || [];
    const newSources = currentSources.includes(source)
      ? currentSources.filter((s) => s !== source)
      : [...currentSources, source];
    onFilterChange({ ...filters, info_sources: newSources });
  };

  // Полный сброс только фильтров, без разрушения пагинации/сортировки в родителе.
  const clearFilters = () => {
    onFilterChange({
      vessel_types: [],
      flags: [],
      info_sources: [],
      year_from: undefined,
      year_to: undefined,
    });
  };

  // Вычисляем, есть ли активные ограничения, чтобы показывать кнопку "Сбросить".
  const hasActiveFilters =
    (filters.vessel_types?.length || 0) > 0 ||
    (filters.flags?.length || 0) > 0 ||
    (filters.info_sources?.length || 0) > 0 ||
    filters.year_from !== undefined ||
    filters.year_to !== undefined;

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-100">Фильтры</h3>
        <div className="flex gap-2">
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="text-sm text-blue-400 hover:text-blue-300"
            >
              Сбросить
            </button>
          )}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-gray-400 hover:text-gray-300"
          >
            {isExpanded ? "▲" : "▼"}
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="space-y-6">
          {/* Тип судна */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Тип судна ({filters.vessel_types?.length || 0} выбрано)
            </label>
            <div className="max-h-48 overflow-y-auto space-y-2 border border-dark-border rounded p-2">
              {vesselTypes.map((type) => (
                <label
                  key={type}
                  className="flex items-center space-x-2 hover:bg-dark-hover p-1 rounded cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={filters.vessel_types?.includes(type) || false}
                    onChange={() => handleTypeChange(type)}
                    className="w-4 h-4 rounded border-gray-600 bg-dark-bg text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm text-gray-300">{type}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Флаг */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Флаг ({filters.flags?.length || 0} выбрано)
            </label>
            <div className="max-h-48 overflow-y-auto space-y-2 border border-dark-border rounded p-2">
              {flags.map((flag) => (
                <label
                  key={flag}
                  className="flex items-center space-x-2 hover:bg-dark-hover p-1 rounded cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={filters.flags?.includes(flag) || false}
                    onChange={() => handleFlagChange(flag)}
                    className="w-4 h-4 rounded border-gray-600 bg-dark-bg text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm text-gray-300">{flag}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Источник данных */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Источник данных ({filters.info_sources?.length || 0} выбрано)
            </label>
            <div className="max-h-48 overflow-y-auto space-y-2 border border-dark-border rounded p-2">
              {sources.map((source) => (
                <label
                  key={source}
                  className="flex items-center space-x-2 hover:bg-dark-hover p-1 rounded cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={filters.info_sources?.includes(source) || false}
                    onChange={() => handleSourceChange(source)}
                    className="w-4 h-4 rounded border-gray-600 bg-dark-bg text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm text-gray-300">{source}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Год постройки */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Год постройки
            </label>
            <div className="flex gap-2">
              <input
                type="number"
                placeholder="От"
                value={filters.year_from || ""}
                onChange={(e) =>
                  onFilterChange({
                    ...filters,
                    year_from: e.target.value
                      ? parseInt(e.target.value)
                      : undefined,
                  })
                }
                className="w-1/2 px-3 py-2 bg-dark-bg border border-dark-border rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                type="number"
                placeholder="До"
                value={filters.year_to || ""}
                onChange={(e) =>
                  onFilterChange({
                    ...filters,
                    year_to: e.target.value
                      ? parseInt(e.target.value)
                      : undefined,
                  })
                }
                className="w-1/2 px-3 py-2 bg-dark-bg border border-dark-border rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default FilterPanel;
