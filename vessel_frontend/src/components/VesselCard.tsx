import React from 'react';
import { useNavigate } from 'react-router-dom';
import { vesselApi } from '../api/vesselApi';
import type { Vessel } from '../types/vessel';

interface VesselCardProps {
  vessel: Vessel;
}

const VesselCard: React.FC<VesselCardProps> = ({ vessel }) => {
  const navigate = useNavigate();
  const imageUrl = vesselApi.getImageUrl(vessel.photo_path);
  const vesselId = vessel.imo || vessel.mmsi;

  return (
    <div
      onClick={() => navigate(`/vessel/${vesselId}`)}
      className="bg-dark-card border border-dark-border rounded-lg overflow-hidden hover:border-blue-500 transition-colors cursor-pointer"
    >
      {imageUrl && (
        <div className="w-full h-48 bg-dark-bg">
          <img
            src={imageUrl}
            alt={vessel.name}
            className="w-full h-full object-cover"
            onError={(e) => {
              e.currentTarget.style.display = 'none';
            }}
          />
        </div>
      )}
      <div className="p-4 space-y-2">
        <h3 className="text-lg font-semibold text-gray-100 truncate">{vessel.name}</h3>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span className="text-gray-500">IMO:</span>
            <span className="ml-2 text-gray-300">{vessel.imo}</span>
          </div>
          <div>
            <span className="text-gray-500">MMSI:</span>
            <span className="ml-2 text-gray-300">{vessel.mmsi}</span>
          </div>
          <div>
            <span className="text-gray-500">Тип:</span>
            <span className="ml-2 text-gray-300">{vessel.general_type}</span>
          </div>
          <div>
            <span className="text-gray-500">Флаг:</span>
            <span className="ml-2 text-gray-300">{vessel.flag}</span>
          </div>
          {vessel.year_built && (
            <div>
              <span className="text-gray-500">Год:</span>
              <span className="ml-2 text-gray-300">{vessel.year_built}</span>
            </div>
          )}
          {vessel.length && (
            <div>
              <span className="text-gray-500">Длина:</span>
              <span className="ml-2 text-gray-300">{vessel.length} м</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VesselCard;
