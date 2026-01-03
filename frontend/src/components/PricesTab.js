// Example: How to integrate CountryFilter in your PricesTab.js

import React, { useState, useEffect } from 'react';
import CountryFilter from './CountryFilter';
import './country-filter.css';

const PricesTab = () => {
  const [data, setData] = useState(null);
  const [country, setCountry] = useState('ALL'); // ALL, AU, NZ
  const [loading, setLoading] = useState(true);

  // Fetch data with country filter
  const fetchData = async () => {
    try {
      const response = await fetch(`/api/ai-prices/?country=${country}`);
      const result = await response.json();
      setData(result);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching data:', error);
      setLoading(false);
    }
  };

  // Refetch when country changes
  useEffect(() => {
    fetchData();
  }, [country]);

  // Auto-refresh every 60s
  useEffect(() => {
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [country]);

  if (loading) {
    return <div className="loading">Loading...</div>;
  }

  return (
    <div className="prices-tab">
      {/* Country Filter Toggle */}
      <CountryFilter 
        selected={country}
        onChange={setCountry}
        counts={{
          au: data?.summary?.au_meetings || 0,
          nz: data?.summary?.nz_meetings || 0
        }}
      />

      {/* Country Stats */}
      <div className="country-stats">
        <div className="stat-item">
          <span className="stat-flag">🇦🇺</span>
          <span className="stat-count">{data?.summary?.au_meetings || 0}</span>
          <span className="stat-label">AU Meetings</span>
        </div>
        <div className="stat-item">
          <span className="stat-flag">🇳🇿</span>
          <span className="stat-count">{data?.summary?.nz_meetings || 0}</span>
          <span className="stat-label">NZ Meetings</span>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{data?.summary?.total_jockey_meetings || 0}</div>
          <div className="stat-label">Jockey Meetings</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data?.summary?.total_driver_meetings || 0}</div>
          <div className="stat-label">Driver Meetings</div>
        </div>
        <div className="stat-card highlight">
          <div className="stat-value">{data?.summary?.total_value_bets || 0}</div>
          <div className="stat-label">Value Bets</div>
        </div>
      </div>

      {/* Jockey Challenges */}
      <h2>🏇 Jockey Challenges</h2>
      {data?.jockey_challenges?.length === 0 ? (
        <p className="no-data">No jockey meetings available</p>
      ) : (
        data?.jockey_challenges?.map((meeting, idx) => (
          <div key={idx} className="meeting-card">
            <div className="meeting-header">
              <div className="meeting-title">
                <span className="meeting-name">{meeting.meeting}</span>
                <span className={`country-badge ${meeting.country?.toLowerCase()}`}>
                  {meeting.country === 'NZ' ? '🇳🇿 NZ' : '🇦🇺 AU'}
                </span>
              </div>
              <span className="source-badge">{meeting.source}</span>
            </div>
            
            <table className="participants-table">
              <thead>
                <tr>
                  <th>Jockey</th>
                  <th>Odds</th>
                  <th>AI Price</th>
                  <th>Edge</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                {meeting.participants?.map((p, i) => (
                  <tr key={i} className={p.value === 'YES' ? 'value-row' : ''}>
                    <td>{p.name}</td>
                    <td>${p.tab_odds?.toFixed(2)}</td>
                    <td>${p.ai_price?.toFixed(2)}</td>
                    <td className={p.edge > 0 ? 'positive' : 'negative'}>
                      {p.edge > 0 ? '+' : ''}{p.edge?.toFixed(1)}%
                    </td>
                    <td>
                      {p.value === 'YES' ? (
                        <span className="value-yes">✅ VALUE</span>
                      ) : (
                        <span className="value-no">❌</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))
      )}

      {/* Driver Challenges */}
      <h2>🏎️ Driver Challenges</h2>
      {data?.driver_challenges?.length === 0 ? (
        <p className="no-data">No driver meetings available</p>
      ) : (
        data?.driver_challenges?.map((meeting, idx) => (
          <div key={idx} className="meeting-card">
            <div className="meeting-header">
              <div className="meeting-title">
                <span className="meeting-name">{meeting.meeting}</span>
                <span className={`country-badge ${meeting.country?.toLowerCase()}`}>
                  {meeting.country === 'NZ' ? '🇳🇿 NZ' : '🇦🇺 AU'}
                </span>
              </div>
              <span className="source-badge">{meeting.source}</span>
            </div>
            
            <table className="participants-table">
              <thead>
                <tr>
                  <th>Driver</th>
                  <th>Odds</th>
                  <th>AI Price</th>
                  <th>Edge</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                {meeting.participants?.map((p, i) => (
                  <tr key={i} className={p.value === 'YES' ? 'value-row' : ''}>
                    <td>{p.name}</td>
                    <td>${p.tab_odds?.toFixed(2)}</td>
                    <td>${p.ai_price?.toFixed(2)}</td>
                    <td className={p.edge > 0 ? 'positive' : 'negative'}>
                      {p.edge > 0 ? '+' : ''}{p.edge?.toFixed(1)}%
                    </td>
                    <td>
                      {p.value === 'YES' ? (
                        <span className="value-yes">✅ VALUE</span>
                      ) : (
                        <span className="value-no">❌</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))
      )}

      {/* Last Updated */}
      <div className="last-updated">
        Last updated: {data?.last_updated ? new Date(data.last_updated).toLocaleTimeString() : 'N/A'}
        {data?.from_cache && <span className="cache-badge">📦 Cached</span>}
      </div>
    </div>
  );
};

export default PricesTab;