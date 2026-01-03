// CountryFilter.js - AU/NZ Toggle Component

import React from 'react';

const CountryFilter = ({ selected, onChange, counts }) => {
  const options = [
    { value: 'ALL', label: '🌏 All', flag: '' },
    { value: 'AU', label: '🇦🇺 AU', flag: '🇦🇺' },
    { value: 'NZ', label: '🇳🇿 NZ', flag: '🇳🇿' }
  ];

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
            {counts && (
              <span className="count">
                {option.value === 'ALL' 
                  ? (counts.au || 0) + (counts.nz || 0)
                  : option.value === 'AU' 
                    ? counts.au || 0 
                    : counts.nz || 0
                }
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
};

export default CountryFilter;

/* 
  CSS to add to your App.css:
  
  .country-filter {
    display: flex;
    justify-content: center;
    margin-bottom: 16px;
  }

  .filter-buttons {
    display: flex;
    gap: 8px;
    background: #1a1a2e;
    padding: 4px;
    border-radius: 12px;
  }

  .filter-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: #888;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .filter-btn:hover {
    background: rgba(255, 255, 255, 0.05);
    color: #fff;
  }

  .filter-btn.active {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: #fff;
  }

  .filter-btn .count {
    background: rgba(255, 255, 255, 0.2);
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 12px;
  }

  .filter-btn.active .count {
    background: rgba(255, 255, 255, 0.3);
  }
*/