import React from 'react';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

const Pagination: React.FC<PaginationProps> = ({ currentPage, totalPages, onPageChange }) => {
  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    const showPages = 5;

    if (totalPages <= showPages + 2) {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      pages.push(1);

      let start = Math.max(2, currentPage - 1);
      let end = Math.min(totalPages - 1, currentPage + 1);

      if (currentPage <= 3) {
        end = showPages - 1;
      }
      if (currentPage >= totalPages - 2) {
        start = totalPages - showPages + 2;
      }

      if (start > 2) pages.push('...');

      for (let i = start; i <= end; i++) {
        pages.push(i);
      }

      if (end < totalPages - 1) pages.push('...');

      pages.push(totalPages);
    }

    return pages;
  };

  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-center gap-2 mt-6">
      <button
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
        className="px-3 py-2 bg-dark-card border border-dark-border rounded text-gray-300 hover:bg-dark-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        Назад
      </button>

      {getPageNumbers().map((page, idx) => (
        <React.Fragment key={idx}>
          {page === '...' ? (
            <span className="px-3 py-2 text-gray-500">...</span>
          ) : (
            <button
              onClick={() => onPageChange(page as number)}
              className={`px-3 py-2 rounded transition-colors ${
                currentPage === page
                  ? 'bg-blue-600 text-white'
                  : 'bg-dark-card border border-dark-border text-gray-300 hover:bg-dark-hover'
              }`}
            >
              {page}
            </button>
          )}
        </React.Fragment>
      ))}

      <button
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        className="px-3 py-2 bg-dark-card border border-dark-border rounded text-gray-300 hover:bg-dark-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        Вперед
      </button>
    </div>
  );
};

export default Pagination;
