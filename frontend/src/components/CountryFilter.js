// src/components/CountryFilter.js
// AU/NZ Country Toggle Component

import React from 'react';

const CountryFilter = ({ selected, onChange, counts }) => {
  const options = [
    { value: 'ALL', label: '🌏 All' },
    { value: 'AU', label: '🇦🇺 Australia' },
    { value: 'NZ', label: '🇳🇿 New Zealand' }
  ];

  const getCount = (value) => {
    if (!counts) return 0;
    if (value === 'ALL') return (counts.au || 0) + (counts.nz || 0);
    if (value === 'AU') return counts.au || 0;
    if (value === 'NZ') return counts.nz || 0;
    return 0;
  };

  return (
    <div className="country-filter">
      <div className="filter-buttons">
        {options.map(option => (
          <button
            key={option.value}
            className={`filter-btn ${selected === option.value ? 'active' : ''}`}
            onClick={() => onChange(option.value)}
          >
            {option.label}
            <span className="count">{getCount(option.value)}</span>
          </button>
        ))}
      </div>
    </div>
  );
};

export default CountryFilter;