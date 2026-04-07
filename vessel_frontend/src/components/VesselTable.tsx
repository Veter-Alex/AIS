import React from "react";
import { useNavigate } from "react-router-dom";
import type { Vessel } from "../types/vessel";

interface VesselTableProps {
  vessels: Vessel[];
  sortBy: string;
  sortOrder: "asc" | "desc";
  onSort: (field: string) => void;
}

// Табличное представление судов с клиентской индикацией сортировки.
// Сама сортировка выполняется на стороне API, а таблица отображает текущий state.
const VesselTable: React.FC<VesselTableProps> = ({
  vessels,
  sortBy,
  sortOrder,
  onSort,
}) => {
  const navigate = useNavigate();

  // Иконка сортировки зависит от активного поля и направления.
  const SortIcon = ({ field }: { field: string }) => {
    if (sortBy !== field) return <span className="text-gray-600">⇅</span>;
    return sortOrder === "asc" ? (
      <span className="text-blue-400">▲</span>
    ) : (
      <span className="text-blue-400">▼</span>
    );
  };

  const columns = [
    { key: "name", label: "Название" },
    { key: "imo", label: "IMO" },
    { key: "mmsi", label: "MMSI" },
    { key: "general_type", label: "Тип" },
    { key: "flag", label: "Флаг" },
    { key: "year_built", label: "Год" },
    { key: "length", label: "Длина (м)" },
    { key: "width", label: "Ширина (м)" },
    { key: "gt", label: "GT" },
    { key: "dwt", label: "DWT" },
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-dark-hover border-b border-dark-border">
            {columns.map((col) => (
              <th
                key={col.key}
                onClick={() => onSort(col.key)}
                className="px-4 py-3 text-left text-sm font-semibold text-gray-300 cursor-pointer hover:bg-dark-bg transition-colors"
              >
                <div className="flex items-center gap-2">
                  {col.label}
                  <SortIcon field={col.key} />
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {vessels.map((vessel) => (
            <tr
              key={vessel.id}
              onClick={() => navigate(`/vessel/${vessel.imo}`)}
              className="border-b border-dark-border hover:bg-dark-hover cursor-pointer transition-colors"
            >
              <td className="px-4 py-3 text-sm text-gray-300">{vessel.name}</td>
              <td className="px-4 py-3 text-sm text-gray-400">{vessel.imo}</td>
              <td className="px-4 py-3 text-sm text-gray-400">{vessel.mmsi}</td>
              <td className="px-4 py-3 text-sm text-gray-300">
                {vessel.general_type}
              </td>
              <td className="px-4 py-3 text-sm text-gray-300">{vessel.flag}</td>
              <td className="px-4 py-3 text-sm text-gray-400">
                {vessel.year_built || "-"}
              </td>
              <td className="px-4 py-3 text-sm text-gray-400">
                {vessel.length || "-"}
              </td>
              <td className="px-4 py-3 text-sm text-gray-400">
                {vessel.width || "-"}
              </td>
              <td className="px-4 py-3 text-sm text-gray-400">
                {vessel.gt || "-"}
              </td>
              <td className="px-4 py-3 text-sm text-gray-400">
                {vessel.dwt || "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default VesselTable;
