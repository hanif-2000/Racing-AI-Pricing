import React, { useState, useEffect } from 'react';

const LiveTracker = ({ data }) => {
  const baseUrl = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000';
  
  const [trackers, setTrackers] = useState({});
  const [selectedMeeting, setSelectedMeeting] = useState(null);
  const [trackerData, setTrackerData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [raceInput, setRaceInput] = useState({ race_num: 1, results: [] });

  // Get available meetings from passed data prop
  const availableMeetings = React.useMemo(() => {
    if (!data) return [];
    const meetings = [];
    (data.jockey_challenges || []).forEach(m => {
      meetings.push({ name: m.meeting, type: 'jockey', source: m.source, participants: m.participants });
    });
    (data.driver_challenges || []).forEach(m => {
      meetings.push({ name: m.meeting, type: 'driver', source: m.source, participants: m.participants });
    });
    // Remove duplicates by name+type
    const unique = meetings.filter((m, i, arr) => 
      arr.findIndex(x => x.name === m.name && x.type === m.type) === i
    );
    return unique;
  }, [data]);

  // Fetch all active trackers on mount
  useEffect(() => {
    fetch(`${baseUrl}/api/live-tracker/`)
      .then(res => res.json())
      .then(result => {
        if (result.success) {
          setTrackers(result.trackers || {});
        }
      })
      .catch(err => console.log('No active trackers'));
  }, [baseUrl]);

  // Initialize tracker for a meeting
  const initTracker = async (meeting, type) => {
    setLoading(true);
    try {
      const res = await fetch(`${baseUrl}/api/live-tracker/init/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meeting, type, total_races: 8 })
      });
      const result = await res.json();
      if (result.success) {
        setTrackerData(result);
        setSelectedMeeting(meeting);
        setTrackers(prev => ({ ...prev, [meeting]: result }));
      } else {
        alert(result.error || 'Failed to initialize tracker');
      }
    } catch (err) {
      alert('Error: ' + err.message);
    }
    setLoading(false);
  };

  // Load existing tracker
  const loadTracker = async (meeting) => {
    setLoading(true);
    try {
      const res = await fetch(`${baseUrl}/api/live-tracker/${meeting}/`);
      const result = await res.json();
      if (result.success) {
        setTrackerData(result);
        setSelectedMeeting(meeting);
      }
    } catch (err) {
      alert('Error: ' + err.message);
    }
    setLoading(false);
  };

  // Update race result
  const updateResult = async () => {
    if (!selectedMeeting) return;
    
    try {
      const res = await fetch(`${baseUrl}/api/live-tracker/update/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          meeting: selectedMeeting,
          race_num: raceInput.race_num,
          results: raceInput.results
        })
      });
      const result = await res.json();
      if (result.success) {
        setTrackerData(result);
        setRaceInput({ race_num: raceInput.race_num + 1, results: [] });
      }
    } catch (err) {
      alert('Error: ' + err.message);
    }
  };

  // Add result entry
  const addResultEntry = (position, name) => {
    setRaceInput(prev => ({
      ...prev,
      results: [...prev.results, { position, jockey: name }]
    }));
  };

  // Reset tracker
  const resetTracker = () => {
    setTrackerData(null);
    setSelectedMeeting(null);
    setRaceInput({ race_num: 1, results: [] });
  };

  return (
    <div className="live-tracker">
      <h2 className="section-title">🏇 Live Challenge Tracker</h2>
      
      {/* Meeting Selection */}
      <div className="card" style={{ marginBottom: '20px' }}>
        <h3>Select Meeting to Track</h3>
        {availableMeetings.length === 0 ? (
          <p style={{ color: '#888' }}>Loading meetings... Make sure data is loaded from AI Prices tab first.</p>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginTop: '15px' }}>
            {availableMeetings.map((m, i) => (
              <button
                key={i}
                onClick={() => trackers[m.name] ? loadTracker(m.name) : initTracker(m.name, m.type)}
                style={{
                  padding: '10px 16px',
                  borderRadius: '8px',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: '500',
                  background: selectedMeeting === m.name 
                    ? 'linear-gradient(135deg, #f59e0b, #d97706)'
                    : trackers[m.name] 
                      ? 'linear-gradient(135deg, #10b981, #059669)' 
                      : 'linear-gradient(135deg, #3b82f6, #2563eb)',
                  color: 'white',
                  transition: 'transform 0.2s, box-shadow 0.2s'
                }}
                onMouseOver={e => e.target.style.transform = 'scale(1.05)'}
                onMouseOut={e => e.target.style.transform = 'scale(1)'}
              >
                {m.name} ({m.type === 'jockey' ? '🏇' : '🏎️'}) {trackers[m.name] ? '✓' : ''}
              </button>
            ))}
          </div>
        )}
      </div>

      {loading && <div style={{ textAlign: 'center', padding: '20px' }}>⏳ Loading...</div>}

      {/* Tracker Display */}
      {trackerData && (
        <div>
          {/* Header */}
          <div className="card" style={{ marginBottom: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h2 style={{ margin: 0 }}>{trackerData.meeting} - {trackerData.type?.toUpperCase()} CHALLENGE</h2>
                <p style={{ color: '#888', margin: '5px 0 0' }}>
                  Status: <span style={{ 
                    color: trackerData.status === 'in_progress' ? '#f59e0b' : 
                           trackerData.status === 'completed' ? '#10b981' : '#888',
                    fontWeight: 'bold'
                  }}>
                    {trackerData.status?.toUpperCase()}
                  </span> | 
                  Races: <strong>{trackerData.races_completed}/{trackerData.total_races}</strong>
                </p>
              </div>
              <button
                onClick={resetTracker}
                style={{
                  padding: '8px 16px',
                  background: '#374151',
                  border: 'none',
                  borderRadius: '6px',
                  color: 'white',
                  cursor: 'pointer'
                }}
              >
                ← Back to Meetings
              </button>
            </div>
          </div>

          {/* Standings Table */}
          <div className="card" style={{ marginBottom: '20px', overflowX: 'auto' }}>
            <h3>📊 Current Standings</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '15px' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #374151' }}>
                  <th style={{ textAlign: 'left', padding: '12px 10px', color: '#9ca3af' }}>Name</th>
                  <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>Rides Done</th>
                  <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>Rides Left</th>
                  <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>Wins</th>
                  <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>2nds</th>
                  <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>Points</th>
                  <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>Last Race</th>
                  <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>AI Win %</th>
                  <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>AI Price</th>
                  <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {(trackerData.standings || []).map((s, i) => (
                  <tr key={i} style={{ 
                    borderBottom: '1px solid #374151',
                    background: s.is_leader ? 'rgba(245, 158, 11, 0.15)' : 'transparent'
                  }}>
                    <td style={{ padding: '12px 10px', fontWeight: '600', fontSize: '15px' }}>{s.name}</td>
                    <td style={{ textAlign: 'center', padding: '12px 10px' }}>{s.rides_done}</td>
                    <td style={{ textAlign: 'center', padding: '12px 10px' }}>{s.rides_left}</td>
                    <td style={{ textAlign: 'center', padding: '12px 10px', color: '#10b981', fontWeight: '600' }}>{s.wins}</td>
                    <td style={{ textAlign: 'center', padding: '12px 10px', color: '#3b82f6' }}>{s.seconds}</td>
                    <td style={{ textAlign: 'center', padding: '12px 10px', fontWeight: 'bold', fontSize: '16px' }}>{s.points}</td>
                    <td style={{ textAlign: 'center', padding: '12px 10px' }}>
                      {s.last_race_points > 0 ? (
                        <span style={{ 
                          color: '#10b981', 
                          fontWeight: '600',
                          background: 'rgba(16, 185, 129, 0.2)',
                          padding: '2px 8px',
                          borderRadius: '4px'
                        }}>+{s.last_race_points}</span>
                      ) : <span style={{ color: '#666' }}>0</span>}
                    </td>
                    <td style={{ textAlign: 'center', padding: '12px 10px' }}>{s.ai_win_pct}%</td>
                    <td style={{ textAlign: 'center', padding: '12px 10px', color: '#10b981', fontWeight: '600' }}>
                      ${s.ai_price?.toFixed(2)}
                    </td>
                    <td style={{ textAlign: 'center', padding: '12px 10px' }}>
                      {s.is_leader && (
                        <span style={{ 
                          background: 'linear-gradient(135deg, #f59e0b, #d97706)', 
                          color: 'black', 
                          padding: '4px 10px', 
                          borderRadius: '4px',
                          fontSize: '12px',
                          fontWeight: 'bold'
                        }}>🏆 LEADER</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Race Progression */}
          {trackerData.races_completed > 0 && (
            <div className="card" style={{ marginBottom: '20px', overflowX: 'auto' }}>
              <h3>📈 Race-by-Race Progression</h3>
              <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '15px' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #374151' }}>
                    <th style={{ textAlign: 'left', padding: '12px 10px', color: '#9ca3af' }}>Name</th>
                    {[...Array(trackerData.races_completed || 0)].map((_, i) => (
                      <th key={i} style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>R{i + 1}</th>
                    ))}
                    <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {(trackerData.progression || []).map((p, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #374151' }}>
                      <td style={{ padding: '12px 10px', fontWeight: '500' }}>{p.name}</td>
                      {[...Array(trackerData.races_completed || 0)].map((_, j) => {
                        const race = p.races[`R${j + 1}`];
                        return (
                          <td key={j} style={{ textAlign: 'center', padding: '12px 10px' }}>
                            {race ? (
                              <span style={{ 
                                color: race.gained > 0 ? '#10b981' : '#666',
                                fontWeight: race.gained > 0 ? '600' : '400'
                              }}>
                                {race.display}
                              </span>
                            ) : '-'}
                          </td>
                        );
                      })}
                      <td style={{ textAlign: 'center', padding: '12px 10px', fontWeight: 'bold', fontSize: '16px' }}>{p.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Value Bets */}
          {trackerData.value_bets?.length > 0 && (
            <div className="card" style={{ marginBottom: '20px' }}>
              <h3>💰 Value Bets (Edge &gt; 10%)</h3>
              <div style={{ marginTop: '15px' }}>
                {trackerData.value_bets.map((vb, i) => (
                  <div key={i} style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '15px',
                    background: 'rgba(16, 185, 129, 0.15)',
                    padding: '12px 16px',
                    borderRadius: '8px',
                    marginBottom: '10px',
                    border: '1px solid rgba(16, 185, 129, 0.3)'
                  }}>
                    <span style={{ fontWeight: '600', fontSize: '15px' }}>{vb.participant}</span>
                    <span style={{ 
                      color: '#888',
                      background: '#1f2937',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontSize: '12px'
                    }}>{vb.bookmaker}</span>
                    <span style={{ fontWeight: '500' }}>${vb.bookmaker_odds.toFixed(2)}</span>
                    <span style={{ color: '#666' }}>→</span>
                    <span style={{ color: '#10b981', fontWeight: '600' }}>AI ${vb.ai_price.toFixed(2)}</span>
                    <span style={{ 
                      background: 'linear-gradient(135deg, #10b981, #059669)', 
                      padding: '4px 10px', 
                      borderRadius: '4px',
                      fontSize: '12px',
                      fontWeight: 'bold'
                    }}>🔥 {vb.edge}% EDGE</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Update Race Result */}
          <div className="card">
            <h3>🏁 Enter Race {raceInput.race_num} Results</h3>
            
            <div style={{ marginTop: '20px', marginBottom: '20px' }}>
              <p style={{ color: '#9ca3af', marginBottom: '15px' }}>
                Click jockeys in finishing order (1st place first, then 2nd, then 3rd...):
              </p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                {(trackerData.standings || []).map((s, i) => {
                  const isSelected = raceInput.results.some(r => r.jockey === s.name);
                  const position = raceInput.results.findIndex(r => r.jockey === s.name) + 1;
                  
                  return (
                    <button
                      key={i}
                      onClick={() => !isSelected && addResultEntry(raceInput.results.length + 1, s.name)}
                      disabled={isSelected}
                      style={{
                        padding: '10px 16px',
                        background: isSelected 
                          ? position === 1 ? '#f59e0b' 
                          : position === 2 ? '#9ca3af' 
                          : position === 3 ? '#b45309' 
                          : '#3b82f6'
                          : '#1f2937',
                        border: '1px solid #374151',
                        borderRadius: '8px',
                        color: isSelected && position <= 3 ? 'black' : 'white',
                        cursor: isSelected ? 'default' : 'pointer',
                        fontWeight: isSelected ? '600' : '400',
                        opacity: isSelected ? 0.9 : 1
                      }}
                    >
                      {isSelected && <span style={{ marginRight: '5px' }}>{position}.</span>}
                      {s.name}
                    </button>
                  );
                })}
              </div>
            </div>
            
            {raceInput.results.length > 0 && (
              <div style={{ marginBottom: '20px' }}>
                <p style={{ marginBottom: '10px', fontWeight: '500' }}>Race {raceInput.race_num} Results:</p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', alignItems: 'center' }}>
                  {raceInput.results.map((r, i) => (
                    <span key={i} style={{
                      background: i === 0 ? 'linear-gradient(135deg, #f59e0b, #d97706)' 
                               : i === 1 ? 'linear-gradient(135deg, #9ca3af, #6b7280)' 
                               : i === 2 ? 'linear-gradient(135deg, #b45309, #92400e)' 
                               : 'linear-gradient(135deg, #3b82f6, #2563eb)',
                      color: i <= 2 ? 'black' : 'white',
                      padding: '8px 14px',
                      borderRadius: '8px',
                      fontWeight: '600',
                      fontSize: '14px'
                    }}>
                      {r.position === 1 ? '🥇' : r.position === 2 ? '🥈' : r.position === 3 ? '🥉' : `${r.position}.`} {r.jockey}
                    </span>
                  ))}
                  <button
                    onClick={() => setRaceInput(prev => ({ ...prev, results: [] }))}
                    style={{
                      padding: '8px 14px',
                      background: '#ef4444',
                      border: 'none',
                      borderRadius: '8px',
                      color: 'white',
                      cursor: 'pointer',
                      fontWeight: '500'
                    }}
                  >
                    Clear All
                  </button>
                </div>
              </div>
            )}
            
            <div style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
              <button
                onClick={updateResult}
                disabled={raceInput.results.length < 3}
                style={{
                  padding: '14px 28px',
                  background: raceInput.results.length >= 3 
                    ? 'linear-gradient(135deg, #10b981, #059669)' 
                    : '#374151',
                  border: 'none',
                  borderRadius: '8px',
                  color: 'white',
                  cursor: raceInput.results.length >= 3 ? 'pointer' : 'not-allowed',
                  fontWeight: '600',
                  fontSize: '15px'
                }}
              >
                ✓ Submit Race {raceInput.race_num} Results
              </button>
              
              <span style={{ color: '#666', fontSize: '14px' }}>
                {raceInput.results.length < 3 
                  ? `Select at least ${3 - raceInput.results.length} more position(s)` 
                  : '✓ Ready to submit'}
              </span>
            </div>
          </div>

          {/* Final Results - Show when completed */}
          {trackerData.status === 'completed' && (
            <div className="card" style={{ marginTop: '20px', background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1), rgba(5, 150, 105, 0.1))', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
              <h3>🏆 Final Results</h3>
              <div style={{ marginTop: '15px' }}>
                {(trackerData.standings || []).slice(0, 3).map((s, i) => (
                  <div key={i} style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '15px',
                    padding: '12px 16px',
                    background: i === 0 ? 'rgba(245, 158, 11, 0.2)' : 'rgba(255,255,255,0.05)',
                    borderRadius: '8px',
                    marginBottom: '10px'
                  }}>
                    <span style={{ fontSize: '24px' }}>
                      {i === 0 ? '🥇' : i === 1 ? '🥈' : '🥉'}
                    </span>
                    <span style={{ fontWeight: '600', fontSize: '16px', flex: 1 }}>{s.name}</span>
                    <span style={{ fontWeight: 'bold', fontSize: '18px' }}>{s.points} pts</span>
                    <span style={{ color: '#888' }}>({s.wins} wins)</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default LiveTracker;