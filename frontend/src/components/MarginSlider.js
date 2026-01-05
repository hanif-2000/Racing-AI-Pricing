// src/components/MarginSlider.js
// Adjustable market margin slider (100% - 150%)

import React from 'react';

function MarginSlider({ value, onChange, disabled = false }) {
  const percentage = Math.round(value * 100);
  
  const getColor = () => {
    if (percentage <= 110) return '#22c55e'; // Green - low margin
    if (percentage <= 125) return '#eab308'; // Yellow - medium
    return '#ef4444'; // Red - high margin
  };

  return (
    <div className="margin-slider">
      <div className="margin-header">
        <label>Market Margin</label>
        <span className="margin-value" style={{ color: getColor() }}>
          {percentage}%
        </span>
      </div>
      
      <div className="slider-container">
        <input
          type="range"
          min="100"
          max="150"
          step="5"
          value={percentage}
          onChange={(e) => onChange(parseInt(e.target.value) / 100)}
          disabled={disabled}
          className="slider"
          style={{
            background: `linear-gradient(to right, ${getColor()} 0%, ${getColor()} ${(percentage - 100) * 2}%, #374151 ${(percentage - 100) * 2}%, #374151 100%)`
          }}
        />
        <div className="slider-labels">
          <span>100%</span>
          <span>125%</span>
          <span>150%</span>
        </div>
      </div>
      
      <p className="margin-hint">
        {percentage <= 110 && '🎯 Fair odds - minimal edge'}
        {percentage > 110 && percentage <= 125 && '⚖️ Standard bookmaker margin'}
        {percentage > 125 && '💰 High margin - more conservative'}
      </p>
    </div>
  );
}

// CSS for MarginSlider - add to your App.css or create margin-slider.css
export const MarginSliderStyles = `
.margin-slider {
  background: #1e293b;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
}

.margin-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.margin-header label {
  color: #94a3b8;
  font-size: 14px;
  font-weight: 500;
}

.margin-value {
  font-size: 20px;
  font-weight: 700;
}

.slider-container {
  position: relative;
}

.slider {
  width: 100%;
  height: 8px;
  border-radius: 4px;
  appearance: none;
  cursor: pointer;
  outline: none;
}

.slider::-webkit-slider-thumb {
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: white;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
  transition: transform 0.2s;
}

.slider::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}

.slider:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.slider-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 12px;
  color: #64748b;
}

.margin-hint {
  margin-top: 12px;
  font-size: 13px;
  color: #64748b;
  text-align: center;
}
`;

export default MarginSlider;