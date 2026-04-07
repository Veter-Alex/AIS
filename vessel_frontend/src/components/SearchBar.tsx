import React from "react";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSearch: () => void;
}

// Поисковая строка списка судов.
// Компонент изолирует поведение submit, чтобы родитель управлял только состоянием.
const SearchBar: React.FC<SearchBarProps> = ({ value, onChange, onSearch }) => {
  // Единая точка отправки формы: блокируем нативный submit и
  // прокидываем управление в onSearch родительской страницы.
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch();
  };

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="relative">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Поиск по названию, IMO или MMSI..."
          className="w-full px-4 py-3 bg-dark-card border border-dark-border rounded-lg text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          type="submit"
          className="absolute right-2 top-1/2 -translate-y-1/2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors"
        >
          Поиск
        </button>
      </div>
    </form>
  );
};

export default SearchBar;
