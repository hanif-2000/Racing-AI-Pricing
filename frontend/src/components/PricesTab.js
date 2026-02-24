// src/components/PricesTab.js - MULTI-BOOKMAKER WITH CLIENT-SIDE MERGING
// Merges same meetings from different sources into one row with all odds

import React, { useMemo } from 'react';
import CountryFilter from './CountryFilter';
import './country-filter.css';

const PricesTab = ({ data, meetings, challengeType, country, setCountry }) => {
  
  // Bookmaker config with colors
  const bookmakers = [
    { key: 'tab', name: 'TAB', color: '#f97316' },
    { key: 'sportsbet', name: 'Sportsbet', color: '#22c55e' },
    { key: 'pointsbet', name: 'PointsBet', color: '#3b82f6' },
    { key: 'tabtouch', name: 'TABtouch', color: '#8b5cf6' },
    { key: 'ladbrokes', name: 'Ladbrokes', color: '#ef4444' },
    { key: 'elitebet', name: 'Elitebet', color: '#eab308' },
  ];

  // 🔥 MERGE MEETINGS FROM DIFFERENT SOURCES
  const mergeMeetings = (meetingsList) => {
    if (!meetingsList || meetingsList.length === 0) return [];
    
    const meetingMap = {};
    
    meetingsList.forEach(meeting => {
      // Normalize meeting name (handle case differences)
      const meetingKey = meeting.meeting.toUpperCase().trim();
      const source = meeting.source?.toLowerCase() || 'tab';
      
      if (!meetingMap[meetingKey]) {
        // First time seeing this meeting
        meetingMap[meetingKey] = {
          meeting: meeting.meeting,
          type: meeting.type,
          country: meeting.country,
          sources: [source],
          participantsMap: {}
        };
      } else {
        // Add source if not already present
        if (!meetingMap[meetingKey].sources.includes(source)) {
          meetingMap[meetingKey].sources.push(source);
        }
      }
      
      // Merge participants
      meeting.participants?.forEach(p => {
        // Normalize participant name
        const nameKey = p.name.toUpperCase().trim();
        
        if (!meetingMap[meetingKey].participantsMap[nameKey]) {
          meetingMap[meetingKey].participantsMap[nameKey] = {
            name: p.name,
            odds_by_source: {},
            ai_price: p.ai_price,
            fair_prob: p.fair_prob,
            implied_prob: p.implied_prob
          };
        }
        
        // Use all_odds from backend (already merged per-bookmaker) if available
        if (p.all_odds && typeof p.all_odds === 'object') {
          Object.entries(p.all_odds).forEach(([src, srcOdds]) => {
            if (srcOdds > 0) {
              meetingMap[meetingKey].participantsMap[nameKey].odds_by_source[src.toLowerCase()] = srcOdds;
            }
          });
        } else {
          // Fallback: use meeting-level source
          const odds = p.odds || p.tab_odds;
          if (odds) {
            meetingMap[meetingKey].participantsMap[nameKey].odds_by_source[source] = odds;
          }
        }
        
        // Update AI price if better data available
        if (p.ai_price && !meetingMap[meetingKey].participantsMap[nameKey].ai_price) {
          meetingMap[meetingKey].participantsMap[nameKey].ai_price = p.ai_price;
        }
      });
    });
    
    // Convert map back to array and calculate best odds
    return Object.values(meetingMap).map(meeting => {
      const participants = Object.values(meeting.participantsMap).map(p => {
        // Find best odds
        let bestOdds = 0;
        let bestSource = '';
        
        Object.entries(p.odds_by_source).forEach(([source, odds]) => {
          if (odds > bestOdds) {
            bestOdds = odds;
            bestSource = source;
          }
        });
        
        // Calculate edge using best odds
        const edge = p.ai_price && bestOdds ? 
          ((bestOdds - p.ai_price) / p.ai_price * 100).toFixed(1) : 0;
        
        return {
          ...p,
          best_odds: bestOdds,
          best_source: bestSource,
          edge: parseFloat(edge),
          value: parseFloat(edge) > 0 ? 'YES' : 'NO'
        };
      });
      
      // Sort by best odds (favorites first)
      participants.sort((a, b) => a.best_odds - b.best_odds);
      
      return {
        ...meeting,
        participants,
        total_participants: participants.length
      };
    });
  };

  // Filter by country
  const filterByCountry = (meetingsList) => {
    if (!meetingsList) return [];
    if (country === 'ALL') return meetingsList;
    return meetingsList.filter(m => m.country === country);
  };

  // 🔥 Merged and filtered data
  const mergedJockeyMeetings = useMemo(() => {
    const filtered = filterByCountry(data?.jockey_challenges || []);
    return mergeMeetings(filtered);
  }, [data?.jockey_challenges, country]);

  const mergedDriverMeetings = useMemo(() => {
    const filtered = filterByCountry(data?.driver_challenges || []);
    return mergeMeetings(filtered);
  }, [data?.driver_challenges, country]);

  // Count total value bets
  const totalValueBets = useMemo(() => {
    let count = 0;
    [...mergedJockeyMeetings, ...mergedDriverMeetings].forEach(m => {
      m.participants?.forEach(p => {
        if (p.edge > 0) count++;
      });
    });
    return count;
  }, [mergedJockeyMeetings, mergedDriverMeetings]);

  // Format odds display
  const formatOdds = (odds) => {
    if (!odds || odds === 0) return '—';
    return `$${Number(odds).toFixed(2)}`;
  };

  if (!data) {
    return <div className="loading">Loading data...</div>;
  }

  // Render comparison table for a meeting
  const renderComparisonTable = (meeting, type) => {
    // Get bookmakers that have data for this meeting
    const availableBookies = bookmakers.filter(bookie => 
      meeting.sources?.includes(bookie.key)
    );

    return (
      <div key={meeting.meeting} className="meeting-card">
        {/* Header */}
        <div className="meeting-header-comparison">
          <div className="meeting-title-row">
            <span className="meeting-icon">{type === 'jockey' ? '🏇' : '🏎️'}</span>
            <h3>{meeting.meeting}</h3>
            <span className={`country-tag ${meeting.country?.toLowerCase()}`}>
              {meeting.country === 'NZ' ? '🇳🇿 NZ' : '🇦🇺 AU'}
            </span>
            <span className="participant-badge">
              {meeting.total_participants} {type === 'jockey' ? 'jockeys' : 'drivers'}
            </span>
          </div>
          {/* Source badges */}
          <div className="source-badges">
            {availableBookies.map(bookie => (
              <span 
                key={bookie.key}
                className="source-tag"
                style={{ background: bookie.color }}
              >
                {bookie.name}
              </span>
            ))}
          </div>
        </div>

        {/* Comparison Table */}
        <div className="comparison-table-container">
          <table className="comparison-table">
            <thead>
              <tr>
                <th className="name-col">{type === 'jockey' ? 'Jockey' : 'Driver'}</th>
                {availableBookies.map(bookie => (
                  <th 
                    key={bookie.key} 
                    className="odds-col"
                    style={{ color: bookie.color }}
                  >
                    {bookie.name}
                  </th>
                ))}
                <th className="best-col">Best</th>
                <th className="ai-col">AI Price</th>
                <th className="edge-col">Edge</th>
                <th className="value-col">Value</th>
              </tr>
            </thead>
            <tbody>
              {meeting.participants?.map((p, idx) => {
                const isValue = p.edge > 0;
                const edgeClass = p.edge >= 20 ? 'hot' : p.edge >= 10 ? 'good' : 'mild';

                return (
                  <tr key={idx} className={isValue ? 'value-row' : ''}>
                    <td className="name-col">
                      <strong>{p.name}</strong>
                    </td>
                    
                    {/* Odds for each bookmaker */}
                    {availableBookies.map(bookie => {
                      const odds = p.odds_by_source?.[bookie.key];
                      const isBest = odds && odds === p.best_odds;
                      
                      return (
                        <td 
                          key={bookie.key} 
                          className={`odds-col ${isBest ? 'best-highlight' : ''}`}
                        >
                          <span className={isBest ? 'best-odds-text' : ''}>
                            {formatOdds(odds)}
                          </span>
                        </td>
                      );
                    })}
                    
                    {/* Best Odds */}
                    <td className="best-col">
                      <div className="best-odds-display">
                        <span className="best-value">{formatOdds(p.best_odds)}</span>
                        <span 
                          className="best-source"
                          style={{ color: bookmakers.find(b => b.key === p.best_source)?.color }}
                        >
                          {bookmakers.find(b => b.key === p.best_source)?.name}
                        </span>
                      </div>
                    </td>
                    
                    {/* AI Price */}
                    <td className="ai-col">
                      <span className="ai-price">{formatOdds(p.ai_price)}</span>
                    </td>
                    
                    {/* Edge */}
                    <td className="edge-col">
                      <span className={`edge-badge ${p.edge > 0 ? 'positive' : 'negative'}`}>
                        {p.edge > 0 ? '+' : ''}{p.edge}%
                      </span>
                    </td>
                    
                    {/* Value */}
                    <td className="value-col">
                      {isValue ? (
                        <span className={`value-badge ${edgeClass}`}>
                          {p.edge >= 20 ? '🔥🔥🔥' : p.edge >= 10 ? '🔥🔥' : '🔥'} BET
                        </span>
                      ) : (
                        <span className="no-value">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="prices-tab">
      {/* Country Filter */}
      <CountryFilter 
        selected={country}
        onChange={setCountry}
        counts={{
          au: data?.summary?.au_meetings || 0,
          nz: data?.summary?.nz_meetings || 0
        }}
      />

      {/* Stats Row */}
      <div className="stats-row">
        <div className="stat-box">
          <span className="stat-icon">🇦🇺</span>
          <span className="stat-num">{data?.summary?.au_meetings || 0}</span>
          <span className="stat-text">AU</span>
        </div>
        <div className="stat-box">
          <span className="stat-icon">🇳🇿</span>
          <span className="stat-num">{data?.summary?.nz_meetings || 0}</span>
          <span className="stat-text">NZ</span>
        </div>
        <div className="stat-box">
          <span className="stat-icon">🏇</span>
          <span className="stat-num">{mergedJockeyMeetings.length}</span>
          <span className="stat-text">Jockey</span>
        </div>
        <div className="stat-box">
          <span className="stat-icon">🏎️</span>
          <span className="stat-num">{mergedDriverMeetings.length}</span>
          <span className="stat-text">Driver</span>
        </div>
        <div className="stat-box highlight">
          <span className="stat-icon">🎯</span>
          <span className="stat-num">{totalValueBets}</span>
          <span className="stat-text">Value Bets</span>
        </div>
      </div>

      {/* Jockey Challenges */}
      {(challengeType === 'all' || challengeType === 'jockey') && (
        <section className="challenges-section">
          <h2 className="section-title">🏇 Jockey Challenge Odds – Comparison</h2>
          {mergedJockeyMeetings.length === 0 ? (
            <p className="no-data">No jockey meetings available</p>
          ) : (
            mergedJockeyMeetings.map(meeting => renderComparisonTable(meeting, 'jockey'))
          )}
        </section>
      )}

      {/* Driver Challenges */}
      {(challengeType === 'all' || challengeType === 'driver') && (
        <section className="challenges-section">
          <h2 className="section-title">🏎️ Driver Challenge Odds – Comparison</h2>
          {mergedDriverMeetings.length === 0 ? (
            <p className="no-data">No driver meetings available</p>
          ) : (
            mergedDriverMeetings.map(meeting => renderComparisonTable(meeting, 'driver'))
          )}
        </section>
      )}

      {/* Footer */}
      <div className="prices-footer">
        Last updated: {data?.last_updated ? new Date(data.last_updated).toLocaleTimeString() : 'N/A'}
        {data?.from_cache && <span className="cache-tag">📦 Cached</span>}
      </div>
    </div>
  );
};

export default PricesTab;