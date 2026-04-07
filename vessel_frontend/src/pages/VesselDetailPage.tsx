import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { vesselApi } from "../api/vesselApi";
import type { Vessel, VesselUpdate } from "../types/vessel";

// Детальная страница судна с поддержкой inline-редактирования.
//
// Подход:
// - оригинальные данные хранятся в query-кэше;
// - в режиме редактирования работаем с отдельным черновиком editedVessel;
// - на сохранение отправляем только изменившиеся поля (PATCH).
const VesselDetailPage: React.FC = () => {
  const { imo } = useParams<{ imo: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [isEditing, setIsEditing] = useState(false);
  const [editedVessel, setEditedVessel] = useState<Partial<Vessel>>({});

  const {
    data: vessel,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["vessel", imo],
    queryFn: () => vesselApi.getVesselByImo(imo!),
    enabled: !!imo,
  });

  const updateMutation = useMutation({
    mutationFn: (data: VesselUpdate) => vesselApi.updateVessel(imo!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vessel", imo] });
      setIsEditing(false);
    },
  });

  const handleEdit = () => {
    // Инициализируем черновик текущими значениями,
    // чтобы пользователь редактировал локальную копию данных.
    setEditedVessel({
      name: vessel?.name || "",
      imo: vessel?.imo || "",
      mmsi: vessel?.mmsi || "",
      call_sign: vessel?.call_sign || "",
      general_type: vessel?.general_type || "",
      detailed_type: vessel?.detailed_type || "",
      flag: vessel?.flag || "",
      year_built: vessel?.year_built,
      length: vessel?.length,
      width: vessel?.width,
      dwt: vessel?.dwt,
      gt: vessel?.gt,
      home_port: vessel?.home_port || "",
      description: vessel?.description || "",
    });
    setIsEditing(true);
  };

  const handleSave = () => {
    // Формируем патч только из измененных полей.
    // Это уменьшает риск непреднамеренного перезаписывания данных на backend.
    const updates: VesselUpdate = {};

    if (editedVessel.name !== vessel?.name) updates.name = editedVessel.name;
    if (editedVessel.imo !== vessel?.imo) updates.imo = editedVessel.imo;
    if (editedVessel.mmsi !== vessel?.mmsi) updates.mmsi = editedVessel.mmsi;
    if (editedVessel.call_sign !== vessel?.call_sign)
      updates.call_sign = editedVessel.call_sign;
    if (editedVessel.general_type !== vessel?.general_type)
      updates.general_type = editedVessel.general_type;
    if (editedVessel.detailed_type !== vessel?.detailed_type)
      updates.detailed_type = editedVessel.detailed_type;
    if (editedVessel.flag !== vessel?.flag) updates.flag = editedVessel.flag;
    if (editedVessel.year_built !== vessel?.year_built)
      updates.year_built = editedVessel.year_built;
    if (editedVessel.length !== vessel?.length)
      updates.length = editedVessel.length;
    if (editedVessel.width !== vessel?.width)
      updates.width = editedVessel.width;
    if (editedVessel.dwt !== vessel?.dwt) updates.dwt = editedVessel.dwt;
    if (editedVessel.gt !== vessel?.gt) updates.gt = editedVessel.gt;
    if (editedVessel.home_port !== vessel?.home_port)
      updates.home_port = editedVessel.home_port || null;
    if (editedVessel.description !== vessel?.description)
      updates.description = editedVessel.description || null;

    updateMutation.mutate(updates);
  };

  const handleCancel = () => {
    setIsEditing(false);
    setEditedVessel({});
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-dark-bg flex items-center justify-center">
        <div className="text-gray-400 text-xl">Загрузка...</div>
      </div>
    );
  }

  if (error || !vessel) {
    return (
      <div className="min-h-screen bg-dark-bg flex items-center justify-center">
        <div className="text-center">
          <div className="text-red-400 text-xl mb-4">
            {error instanceof Error ? error.message : "Судно не найдено"}
          </div>
          <button
            onClick={() => navigate("/")}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
          >
            Вернуться к списку
          </button>
        </div>
      </div>
    );
  }

  const imageUrl = vesselApi.getImageUrl(vessel.photo_path);

  const renderField = (
    label: string,
    key: keyof Vessel,
    type: "text" | "number" = "text",
  ) => {
    const value = vessel[key];
    const displayValue = value ?? "-";

    // Служебные поля не редактируются с клиента, чтобы не ломать целостность данных.
    if (
      isEditing &&
      key !== "info_source" &&
      key !== "updated_at" &&
      key !== "id" &&
      key !== "photo_path"
    ) {
      if (type === "number") {
        return (
          <div key={label} className="border-b border-dark-border pb-3">
            <label className="text-sm text-gray-500 mb-1 block">{label}</label>
            <input
              type="number"
              value={(editedVessel[key] as number) || ""}
              onChange={(e) =>
                setEditedVessel({
                  ...editedVessel,
                  [key]: e.target.value ? parseInt(e.target.value) : null,
                })
              }
              className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        );
      }

      return (
        <div key={label} className="border-b border-dark-border pb-3">
          <label className="text-sm text-gray-500 mb-1 block">{label}</label>
          <input
            type="text"
            value={(editedVessel[key] as string) || ""}
            onChange={(e) =>
              setEditedVessel({ ...editedVessel, [key]: e.target.value })
            }
            className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      );
    }

    return (
      <div key={label} className="border-b border-dark-border pb-3">
        <div className="text-sm text-gray-500 mb-1">{label}</div>
        <div className="text-lg text-gray-100 font-medium">{displayValue}</div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-dark-bg">
      {/* Header */}
      <header className="bg-dark-card border-b border-dark-border">
        <div className="container mx-auto px-4 py-6">
          <button
            onClick={() => navigate("/")}
            className="mb-4 text-blue-400 hover:text-blue-300 flex items-center gap-2"
          >
            ← Вернуться к списку
          </button>
          <h1 className="text-3xl font-bold text-gray-100">{vessel.name}</h1>
          <p className="text-gray-400 mt-2">
            IMO: {vessel.imo} • MMSI: {vessel.mmsi}
          </p>
        </div>
      </header>

      <div className="container mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Photo */}
          <div className="lg:col-span-1">
            {imageUrl ? (
              <div className="bg-dark-card border border-dark-border rounded-lg overflow-hidden">
                <img
                  src={imageUrl}
                  alt={vessel.name}
                  className="w-full h-auto"
                  onError={(e) => {
                    e.currentTarget.parentElement!.innerHTML =
                      '<div class="p-8 text-center text-gray-500">Фото недоступно</div>';
                  }}
                />
              </div>
            ) : (
              <div className="bg-dark-card border border-dark-border rounded-lg p-8 text-center text-gray-500">
                Фото отсутствует
              </div>
            )}
          </div>

          {/* Details */}
          <div className="lg:col-span-2">
            <div className="bg-dark-card border border-dark-border rounded-lg overflow-hidden">
              <div className="p-6">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-2xl font-semibold text-gray-100">
                    Характеристики судна
                  </h2>
                  {!isEditing ? (
                    <button
                      onClick={handleEdit}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm transition-colors"
                    >
                      Редактировать
                    </button>
                  ) : (
                    <div className="flex gap-3">
                      <button
                        onClick={handleSave}
                        disabled={updateMutation.isPending}
                        className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white rounded-lg text-sm transition-colors"
                      >
                        {updateMutation.isPending
                          ? "Сохранение..."
                          : "Сохранить"}
                      </button>
                      <button
                        onClick={handleCancel}
                        disabled={updateMutation.isPending}
                        className="px-4 py-2 bg-gray-600 hover:bg-gray-700 disabled:bg-gray-500 text-white rounded-lg text-sm transition-colors"
                      >
                        Отмена
                      </button>
                    </div>
                  )}
                </div>

                {updateMutation.isError && (
                  <div className="mb-4 p-3 bg-red-900/20 border border-red-500 rounded text-red-400 text-sm">
                    Ошибка при сохранении:{" "}
                    {updateMutation.error instanceof Error
                      ? updateMutation.error.message
                      : "Неизвестная ошибка"}
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {renderField("Название", "name")}
                  {renderField("IMO", "imo")}
                  {renderField("MMSI", "mmsi")}
                  {renderField("Позывной", "call_sign")}
                  {renderField("Общий тип", "general_type")}
                  {renderField("Детальный тип", "detailed_type")}
                  {renderField("Флаг", "flag")}
                  {renderField("Год постройки", "year_built", "number")}
                  {renderField("Длина (м)", "length", "number")}
                  {renderField("Ширина (м)", "width", "number")}
                  {renderField("Дедвейт (т)", "dwt", "number")}
                  {renderField("Валовая вместимость (GT)", "gt", "number")}
                  {renderField("Порт приписки", "home_port")}
                  {renderField("Источник", "info_source")}
                  {renderField("Обновлено", "updated_at")}
                </div>

                {/* Description Section */}
                <div className="mt-6 pt-6 border-t border-dark-border">
                  <h3 className="text-xl font-semibold text-gray-100 mb-3">
                    Описание
                  </h3>
                  {isEditing ? (
                    <textarea
                      value={(editedVessel.description as string) || ""}
                      onChange={(e) =>
                        setEditedVessel({
                          ...editedVessel,
                          description: e.target.value,
                        })
                      }
                      className="w-full h-40 px-4 py-3 bg-dark-bg border border-dark-border rounded-lg text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                      placeholder="Введите описание судна..."
                    />
                  ) : (
                    <div>
                      {vessel.description ? (
                        <p className="text-gray-300 leading-relaxed whitespace-pre-wrap">
                          {vessel.description}
                        </p>
                      ) : (
                        <p className="text-gray-500 italic">
                          Описание отсутствует
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VesselDetailPage;
