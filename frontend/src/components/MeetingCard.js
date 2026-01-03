// src/components/MeetingCard.js

import React, { useState } from 'react';

function MeetingCard({ meeting }) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const getValueRating = (edge) => {
    if (edge >= 20) return { emoji: '🔥🔥🔥', class: 'value-hot' };
    if (edge >= 10) return { emoji: '🔥🔥', class: 'value-good' };
    if (edge > 0) return { emoji: '🔥', class: 'value-mild' };
    return { emoji: '', class: '' };
  };

  const formatOdds = (odds) => {
    if (!odds || odds === 0) return '—';
    return `$${Number(odds).toFixed(2)}`;
  };

  const getSourceBadge = (source) => {
    const sources = {
      'tab': { name: 'TAB', color: '#f97316' },
      'elitebet': { name: 'Elitebet', color: '#eab308' },
      'sportsbet': { name: 'Sportsbet', color: '#22c55e' },
      'ladbrokes': { name: 'Ladbrokes', color: '#ef4444' },
      'tabtouch': { name: 'TABtouch', color: '#8b5cf6' },
    };
    return sources[source] || { name: source || 'Unknown', color: '#6b7280' };
  };

  const source = getSourceBadge(meeting.source);

  return (
    <div className={`meeting-card ${meeting.type}-card`}>
      <div 
        className="meeting-header"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="meeting-info">
          <span className="meeting-icon">
            {meeting.type === 'jockey' ? '🏇' : '🏎️'}
          </span>
          <h3>{meeting.meeting}</h3>
          <span className="participant-count">
            {meeting.total_participants || meeting.participants?.length || 0} {meeting.type === 'jockey' ? 'jockeys' : 'drivers'}
          </span>
          <span 
            className="source-badge" 
            style={{ backgroundColor: source.color }}
          >
            {source.name}
          </span>
        </div>
        <div className="meeting-actions">
          <span className={`expand-icon ${isExpanded ? 'expanded' : ''}`}>
            ▼
          </span>
        </div>
      </div>

      {isExpanded && (
        <div className="meeting-content">
          <div className="meeting-table-wrapper">
            <table className="meeting-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Name</th>
                  <th className="center">Odds</th>
                  <th className="center">AI Price</th>
                  <th className="center">Fair %</th>
                  <th className="center">Edge</th>
                  <th className="center">Value</th>
                </tr>
              </thead>
              <tbody>
                {meeting.participants?.map((p, idx) => {
                  const rating = getValueRating(p.edge);
                  const isValue = p.value === 'YES' || p.edge > 0;
                  
                  return (
                    <tr key={idx} className={isValue ? 'value-row' : ''}>
                      <td>{idx + 1}</td>
                      <td><strong>{p.name}</strong></td>
                      <td className="center tab-odds">{formatOdds(p.tab_odds)}</td>
                      <td className="center ai-price">{formatOdds(p.ai_price)}</td>
                      <td className="center">{p.fair_prob || 0}%</td>
                      <td className="center">
                        <span className={`edge-badge ${p.edge > 0 ? 'positive' : 'negative'}`}>
                          {p.edge > 0 ? '+' : ''}{p.edge || 0}%
                        </span>
                      </td>
                      <td className="center">
                        {isValue ? (
                          <span className={`action-badge value ${rating.class}`}>
                            {rating.emoji || '✅ BET'}
                          </span>
                        ) : (
                          <span className="action-badge pass">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default MeetingCard;