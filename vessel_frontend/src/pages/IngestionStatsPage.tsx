import { useQuery } from "@tanstack/react-query";
import React from "react";
import { Link } from "react-router-dom";
import { vesselApi } from "../api/vesselApi";
import type { ScraperStateItem } from "../types/vessel";

// Страница мониторинга ingestion: БД и состояние скраперов из `/stats/ingestion`.
// Данные запрашиваются при открытии и при обновлении страницы (без фонового опроса).

function activityLabel(activity: string): string {
  switch (activity) {
    case "recent":
      return "недавняя активность";
    case "stale":
      return "давно не обновлялся";
    case "never":
      return "нет метки времени";
    default:
      return activity;
  }
}

function activityClass(activity: string): string {
  switch (activity) {
    case "recent":
      return "text-emerald-400";
    case "stale":
      return "text-amber-400";
    case "never":
      return "text-gray-500";
    default:
      return "text-gray-400";
  }
}

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function pluralizeRu(
  value: number,
  one: string,
  few: string,
  many: string,
): string {
  const mod10 = value % 10;
  const mod100 = value % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function formatRelativeAgo(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  const diffMs = Date.now() - date.getTime();
  if (diffMs < 0) return "(только что)";
  const diffMinutes = Math.floor(diffMs / 60000);

  if (diffMinutes < 1) return "(только что)";
  if (diffMinutes < 60) {
    return `(${diffMinutes} ${pluralizeRu(diffMinutes, "минута", "минуты", "минут")} назад)`;
  }

  const hours = Math.floor(diffMinutes / 60);
  const minutes = diffMinutes % 60;
  if (hours < 24) {
    if (minutes === 0) {
      return `(${hours} ${pluralizeRu(hours, "час", "часа", "часов")} назад)`;
    }
    return `(${hours} ${pluralizeRu(hours, "час", "часа", "часов")} ${minutes} ${pluralizeRu(minutes, "минута", "минуты", "минут")} назад)`;
  }

  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  if (remHours === 0) {
    return `(${days} ${pluralizeRu(days, "день", "дня", "дней")} назад)`;
  }
  return `(${days} ${pluralizeRu(days, "день", "дня", "дней")} ${remHours} ${pluralizeRu(remHours, "час", "часа", "часов")} назад)`;
}

const ScraperRows: React.FC<{
  rows: ScraperStateItem[];
  showScraperName?: boolean;
}> = ({ rows, showScraperName = false }) => {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-gray-500 py-2">
        Нет строк в <code className="text-gray-400">scraper_state</code> для
        этого источника.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border border-dark-border rounded-lg overflow-hidden">
        <thead className="bg-dark-hover text-gray-400 text-left">
          <tr>
            {showScraperName && (
              <th className="px-3 py-2 font-medium">Скрапер</th>
            )}
            <th className="px-3 py-2 font-medium">Режим</th>
            <th className="px-3 py-2 font-medium">Страница</th>
            <th className="px-3 py-2 font-medium">Судов (счётчик)</th>
            <th className="px-3 py-2 font-medium">Последний запуск</th>
            <th className="px-3 py-2 font-medium">Последняя запись</th>
            <th className="px-3 py-2 font-medium">Активность</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={`${r.scraper_name}-${r.mode}`}
              className="border-t border-dark-border bg-dark-card"
            >
              {showScraperName && (
                <td className="px-3 py-2 font-mono text-gray-200 text-xs">
                  {r.scraper_name}
                </td>
              )}
              <td className="px-3 py-2 font-mono text-gray-200">{r.mode}</td>
              <td className="px-3 py-2 text-gray-300">{r.last_page}</td>
              <td className="px-3 py-2 text-gray-300">{r.vessels_count}</td>
              <td className="px-3 py-2 text-gray-400 font-mono text-xs">
                {formatDateTime(r.last_run_at)}
              </td>
              <td className="px-3 py-2 text-gray-400 font-mono text-xs">
                {formatDateTime(r.last_data_at)}{" "}
                <span className="text-gray-500">
                  {formatRelativeAgo(r.last_data_at)}
                </span>
              </td>
              <td className={`px-3 py-2 ${activityClass(r.activity)}`}>
                {activityLabel(r.activity)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const IngestionStatsPage: React.FC = () => {
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["ingestion-stats"],
    queryFn: vesselApi.getIngestionStats,
  });

  return (
    <div className="min-h-screen bg-dark-bg text-gray-100">
      <header className="bg-dark-card border-b border-dark-border">
        <div className="container mx-auto px-4 py-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold">Мониторинг ingestion</h1>
              <p className="text-sm text-gray-400 mt-1">
                Состояние БД и скраперов по{" "}
                <code className="text-gray-300">scraper_state</code> и{" "}
                <code className="text-gray-300">source_priority</code>.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => refetch()}
                disabled={isFetching}
                className="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {isFetching ? "Обновление…" : "Обновить"}
              </button>
              <Link
                to="/"
                className="px-4 py-2 rounded bg-dark-hover text-gray-300 hover:bg-dark-border border border-dark-border"
              >
                К каталогу
              </Link>
            </div>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8 max-w-5xl">
        {isLoading && (
          <p className="text-gray-400">Загрузка статистики…</p>
        )}
        {error && (
          <p className="text-red-400">
            Ошибка:{" "}
            {error instanceof Error ? error.message : "неизвестная ошибка"}
          </p>
        )}
        {data && (
          <>
            <section className="mb-10 grid gap-4 sm:grid-cols-2">
              <div className="bg-dark-card border border-dark-border rounded-lg p-4">
                <h2 className="text-sm font-medium text-gray-400 mb-2">
                  PostgreSQL
                </h2>
                <p
                  className={
                    data.database.ok ? "text-emerald-400" : "text-red-400"
                  }
                >
                  {data.database.ok ? "Доступна" : "Недоступна"}
                </p>
                {data.database.detail && (
                  <p className="text-xs text-gray-500 mt-2">
                    {data.database.detail}
                  </p>
                )}
              </div>
              <div className="bg-dark-card border border-dark-border rounded-lg p-4">
                <h2 className="text-sm font-medium text-gray-400 mb-2">
                  Каталог судов
                </h2>
                <p className="text-xl text-gray-100">
                  {data.total_vessels != null
                    ? data.total_vessels.toLocaleString()
                    : "—"}
                </p>
                <p className="text-xs text-gray-500 mt-2">
                  Порог «свежести» скрапера: {data.stale_after_minutes} мин.
                </p>
              </div>
            </section>

            <section className="mb-10">
              <h2 className="text-lg font-semibold mb-4">Источники данных</h2>
              <div className="space-y-8">
                {data.sources.map((src) => (
                  <div
                    key={src.source_name}
                    className="bg-dark-card border border-dark-border rounded-lg p-4"
                  >
                    <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
                      <div>
                        <span className="font-mono text-gray-100">
                          {src.source_name}
                        </span>
                        <span className="text-gray-500 text-sm ml-2">
                          приоритет {src.priority}
                          {!src.is_active && (
                            <span className="text-amber-500 ml-2">
                              (неактивен в каталоге)
                            </span>
                          )}
                        </span>
                      </div>
                    </div>
                    {src.description && (
                      <p className="text-sm text-gray-500 mb-3">
                        {src.description}
                      </p>
                    )}
                    <ScraperRows rows={src.scrapers} />
                  </div>
                ))}
              </div>
            </section>

            {data.orphan_scrapers.length > 0 && (
              <section className="mb-10">
                <h2 className="text-lg font-semibold mb-2">
                  Состояние без записи в source_priority
                </h2>
                <p className="text-sm text-gray-500 mb-4">
                  Имя скрапера в <code>scraper_state</code> не совпало ни с
                  одним <code>source_name</code>.
                </p>
                <ScraperRows rows={data.orphan_scrapers} showScraperName />
              </section>
            )}

            <p className="text-xs text-gray-600">
              Снимок: {formatDateTime(data.generated_at)}
            </p>
          </>
        )}
      </div>
    </div>
  );
};

export default IngestionStatsPage;
