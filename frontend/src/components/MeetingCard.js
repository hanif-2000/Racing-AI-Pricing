// src/components/MeetingCard.js - WITH BOOKMAKER COMPARISON

import React, { useState } from 'react';

function MeetingCard({ meeting, showComparison = false }) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const bookmakerColors = {
    'tab': { name: 'TAB', color: '#f97316', bg: '#fff7ed' },
    'sportsbet': { name: 'Sportsbet', color: '#22c55e', bg: '#f0fdf4' },
    'tabtouch': { name: 'TABtouch', color: '#8b5cf6', bg: '#faf5ff' },
    'ladbrokes': { name: 'Ladbrokes', color: '#ef4444', bg: '#fef2f2' },
    'elitebet': { name: 'Elitebet', color: '#eab308', bg: '#fefce8' },
    'pointsbet': { name: 'PointsBet', color: '#3b82f6', bg: '#eff6ff' },
  };

  const getValueRating = (edge) => {
    if (edge >= 20) return { emoji: '🔥🔥🔥', class: 'value-hot', text: 'HOT!' };
    if (edge >= 10) return { emoji: '🔥🔥', class: 'value-good', text: 'Good' };
    if (edge > 0) return { emoji: '🔥', class: 'value-mild', text: 'Value' };
    return { emoji: '', class: '', text: '' };
  };

  const formatOdds = (odds) => {
    if (!odds || odds === 0) return '—';
    return `$${Number(odds).toFixed(2)}`;
  };

  const sources = meeting.sources || [meeting.source];
  const sourceList = sources.map(s => bookmakerColors[s] || { name: s, color: '#6b7280' });

  return (
    <div className={`meeting-card ${meeting.type}-card`}>
      {/* Header */}
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
          
          {/* Source badges */}
          <div className="source-badges">
            {sourceList.map((source, idx) => (
              <span 
                key={idx}
                className="source-badge" 
                style={{ backgroundColor: source.color }}
              >
                {source.name}
              </span>
            ))}
          </div>
        </div>
        
        <div className="meeting-actions">
          <span className={`expand-icon ${isExpanded ? 'expanded' : ''}`}>
            ▼
          </span>
        </div>
      </div>

      {/* Content */}
      {isExpanded && (
        <div className="meeting-content">
          {/* Comparison View - Shows all bookmaker odds */}
          {meeting.participants?.[0]?.odds_by_source ? (
            <ComparisonTable 
              participants={meeting.participants} 
              bookmakerColors={bookmakerColors}
              formatOdds={formatOdds}
              getValueRating={getValueRating}
            />
          ) : (
            // Standard View - Single bookmaker
            <StandardTable 
              participants={meeting.participants}
              formatOdds={formatOdds}
              getValueRating={getValueRating}
            />
          )}
        </div>
      )}
    </div>
  );
}


// =====================================================
// 📊 COMPARISON TABLE - All bookmakers side by side
// =====================================================

function ComparisonTable({ participants, bookmakerColors, formatOdds, getValueRating }) {
  // Get all bookmakers present
  const allBookmakers = new Set();
  participants.forEach(p => {
    if (p.odds_by_source) {
      Object.keys(p.odds_by_source).forEach(b => allBookmakers.add(b));
    }
  });
  const bookmakers = Array.from(allBookmakers);

  return (
    <div className="comparison-table-wrapper">
      <table className="comparison-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Name</th>
            {bookmakers.map(b => (
              <th key={b} style={{ backgroundColor: bookmakerColors[b]?.bg }}>
                <span style={{ color: bookmakerColors[b]?.color, fontWeight: 'bold' }}>
                  {bookmakerColors[b]?.name || b}
                </span>
              </th>
            ))}
            <th className="best-col">Best</th>
            <th className="ai-col">AI Price</th>
            <th className="edge-col">Edge</th>
            <th className="value-col">Value</th>
          </tr>
        </thead>
        <tbody>
          {participants.map((p, idx) => {
            const rating = getValueRating(p.best_edge || p.edge || 0);
            const isValue = (p.best_edge || p.edge || 0) > 0;
            
            return (
              <tr key={idx} className={isValue ? 'value-row' : ''}>
                <td>{idx + 1}</td>
                <td><strong>{p.name}</strong></td>
                
                {/* Odds from each bookmaker */}
                {bookmakers.map(b => {
                  const odds = p.odds_by_source?.[b];
                  const isBest = odds && odds === p.best_odds;
                  return (
                    <td 
                      key={b} 
                      className={`odds-cell ${isBest ? 'best-odds' : ''}`}
                      style={{ backgroundColor: isBest ? bookmakerColors[b]?.bg : '' }}
                    >
                      {formatOdds(odds)}
                      {isBest && <span className="best-marker">★</span>}
                    </td>
                  );
                })}
                
                {/* Best odds */}
                <td className="best-col">
                  <span className="best-odds-value">{formatOdds(p.best_odds)}</span>
                  {p.best_source && (
                    <span 
                      className="best-source"
                      style={{ color: bookmakerColors[p.best_source]?.color }}
                    >
                      {bookmakerColors[p.best_source]?.name}
                    </span>
                  )}
                </td>
                
                {/* AI Price */}
                <td className="ai-col ai-price">{formatOdds(p.ai_price)}</td>
                
                {/* Edge */}
                <td className="edge-col">
                  <span className={`edge-badge ${(p.best_edge || p.edge || 0) > 0 ? 'positive' : 'negative'}`}>
                    {(p.best_edge || p.edge || 0) > 0 ? '+' : ''}{(p.best_edge || p.edge || 0)}%
                  </span>
                </td>
                
                {/* Value */}
                <td className="value-col">
                  {isValue ? (
                    <span className={`action-badge value ${rating.class}`}>
                      {rating.emoji || '✅'} {rating.text}
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
      
      {/* Legend */}
      <div className="comparison-legend">
        <span>★ = Best Available Odds</span>
        <span>|</span>
        <span>🔥 = Value Bet (Edge &gt; 0%)</span>
      </div>
    </div>
  );
}


// =====================================================
// 📋 STANDARD TABLE - Single bookmaker
// =====================================================

function StandardTable({ participants, formatOdds, getValueRating }) {
  return (
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
          {participants?.map((p, idx) => {
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
  );
}


export default MeetingCard;