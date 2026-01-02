import React from 'react';

function StatCard({ icon, label, value, color = 'default' }) {
  return (
    <div className={`stat-card stat-card-${color}`}>
      <span className="stat-icon">{icon}</span>
      <div className="stat-info">
        <p className="stat-label">{label}</p>
        <p className="stat-value">{value}</p>
      </div>
    </div>
  );
}

export default StatCard;
