import React from 'react';
import { vesselApi } from '../api/vesselApi';
import type { VesselFilters } from '../types/vessel';

interface ExportButtonProps {
  filters: VesselFilters;
}

const ExportButton: React.FC<ExportButtonProps> = ({ filters }) => {
  const [isOpen, setIsOpen] = React.useState(false);

  const handleExport = (format: 'csv' | 'json') => {
    const url = vesselApi.exportVessels(format, filters);
    window.open(url, '_blank');
    setIsOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors"
      >
        Экспорт
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute right-0 mt-2 w-48 bg-dark-card border border-dark-border rounded-lg shadow-lg z-20">
            <button
              onClick={() => handleExport('csv')}
              className="w-full px-4 py-2 text-left text-gray-300 hover:bg-dark-hover transition-colors rounded-t-lg"
            >
              Экспорт в CSV
            </button>
            <button
              onClick={() => handleExport('json')}
              className="w-full px-4 py-2 text-left text-gray-300 hover:bg-dark-hover transition-colors rounded-b-lg"
            >
              Экспорт в JSON
            </button>
          </div>
        </>
      )}
    </div>
  );
};

export default ExportButton;
