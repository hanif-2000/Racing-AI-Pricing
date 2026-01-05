import React, { useState, useEffect } from 'react';

const LiveTracker = ({ data }) => {
  const baseUrl = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000';
  
  const [trackers, setTrackers] = useState({});
  const [selectedMeeting, setSelectedMeeting] = useState(null);
  const [trackerData, setTrackerData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [raceInput, setRaceInput] = useState({ race_num: 1, results: [] });
  const [autoFetching, setAutoFetching] = useState(false);
  const [autoStandings, setAutoStandings] = useState(null);

  const availableMeetings = React.useMemo(() => {
    if (!data) return [];
    const meetings = [];
    (data.jockey_challenges || []).forEach(m => {
      meetings.push({ 
        name: m.meeting, 
        type: 'jockey', 
        source: m.source, 
        participants: m.participants,
        jockeys: m.jockeys || m.participants
      });
    });
    (data.driver_challenges || []).forEach(m => {
      meetings.push({ 
        name: m.meeting, 
        type: 'driver', 
        source: m.source, 
        participants: m.participants,
        drivers: m.drivers || m.participants
      });
    });
    const unique = meetings.filter((m, i, arr) => 
      arr.findIndex(x => x.name === m.name && x.type === m.type) === i
    );
    return unique;
  }, [data]);

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

  // 🆕 AUTO FETCH STANDINGS - Uses jockey names from data prop
  const autoFetchStandings = async (meetingName) => {
    setAutoFetching(true);
    
    // Get jockey names from selected meeting data
    const meeting = availableMeetings.find(m => m.name === meetingName);
    const jockeyNames = meeting?.jockeys?.map(j => j.name) || 
                        meeting?.participants?.map(p => p.name) || [];
    
    if (jockeyNames.length === 0) {
      alert('❌ No jockey data found for this meeting');
      setAutoFetching(false);
      return;
    }
    
    try {
      // Call backend with jockey names in body
      const res = await fetch(`${baseUrl}/api/auto-standings/${meetingName}/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jockeys: jockeyNames })
      });
      const result = await res.json();
      
      if (result.success) {
        setAutoStandings(result);
        alert(`✅ Fetched ${result.completed_races?.length || 0} race results from Ladbrokes!`);
      } else {
        alert('❌ ' + (result.error || 'Failed to fetch results'));
      }
    } catch (err) {
      alert('Error: ' + err.message);
    }
    setAutoFetching(false);
  };

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

  const addResultEntry = (position, name) => {
    setRaceInput(prev => ({
      ...prev,
      results: [...prev.results, { position, jockey: name }]
    }));
  };

  const resetTracker = () => {
    setTrackerData(null);
    setSelectedMeeting(null);
    setAutoStandings(null);
    setRaceInput({ race_num: 1, results: [] });
  };

  return (
    <div className="live-tracker">
      <h2 className="section-title">⚡ Live Challenge Tracker</h2>
      
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
                onClick={() => {
                  setSelectedMeeting(m.name);
                  setAutoStandings(null);
                  if (trackers[m.name]) {
                    loadTracker(m.name);
                  } else {
                    initTracker(m.name, m.type);
                  }
                }}
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
                  color: 'white'
                }}
              >
                {m.name} ({m.type === 'jockey' ? '🏇' : '🏎️'}) {trackers[m.name] ? '✓' : ''}
              </button>
            ))}
          </div>
        )}
      </div>

      {loading && <div style={{ textAlign: 'center', padding: '20px' }}>⏳ Loading...</div>}

      {selectedMeeting && (
        <div>
          {/* Header */}
          <div className="card" style={{ marginBottom: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
              <div>
                <h2 style={{ margin: 0 }}>{selectedMeeting} - JOCKEY CHALLENGE</h2>
                <p style={{ color: '#888', margin: '5px 0 0' }}>
                  {autoStandings ? (
                    <>Races: <strong>{autoStandings.completed_races?.length || 0}</strong> completed
                    {autoStandings.last_updated && ` • ${new Date(autoStandings.last_updated).toLocaleTimeString()}`}</>
                  ) : trackerData ? (
                    <>Status: <span style={{ color: '#f59e0b', fontWeight: 'bold' }}>{trackerData.status?.toUpperCase()}</span>
                    {' | '}Races: <strong>{trackerData.races_completed}/{trackerData.total_races}</strong></>
                  ) : 'Loading...'}
                </p>
              </div>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  onClick={() => autoFetchStandings(selectedMeeting)}
                  disabled={autoFetching}
                  style={{
                    padding: '10px 20px',
                    background: autoFetching ? '#374151' : 'linear-gradient(135deg, #10b981, #059669)',
                    border: 'none',
                    borderRadius: '8px',
                    color: 'white',
                    cursor: autoFetching ? 'wait' : 'pointer',
                    fontWeight: '600'
                  }}
                >
                  {autoFetching ? '⏳ Fetching...' : '🔄 Auto Fetch Results'}
                </button>
                <button onClick={resetTracker} style={{
                  padding: '10px 16px', background: '#374151', border: 'none',
                  borderRadius: '8px', color: 'white', cursor: 'pointer'
                }}>← Back</button>
              </div>
            </div>
          </div>

          {/* Auto Standings from Ladbrokes */}
          {autoStandings && (
            <div className="card" style={{ 
              marginBottom: '20px', 
              background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1), rgba(5, 150, 105, 0.05))', 
              border: '1px solid rgba(16, 185, 129, 0.3)' 
            }}>
              <h3 style={{ color: '#10b981' }}>📊 Live Standings (Ladbrokes Results)</h3>
              <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '15px' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #374151' }}>
                    <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af', width: '50px' }}>Rank</th>
                    <th style={{ textAlign: 'left', padding: '12px 10px', color: '#9ca3af' }}>Jockey</th>
                    <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>Points</th>
                    <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>W</th>
                    <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>2nd</th>
                    <th style={{ textAlign: 'center', padding: '12px 10px', color: '#9ca3af' }}>3rd</th>
                    <th style={{ textAlign: 'left', padding: '12px 10px', color: '#9ca3af' }}>Race Points</th>
                  </tr>
                </thead>
                <tbody>
                  {autoStandings.standings?.map((s, i) => (
                    <tr key={i} style={{ 
                      borderBottom: '1px solid #374151',
                      background: s.is_leader ? 'rgba(245, 158, 11, 0.2)' : 'transparent'
                    }}>
                      <td style={{ textAlign: 'center', padding: '12px', fontWeight: 'bold', fontSize: '16px' }}>
                        {s.is_leader ? '👑' : i + 1}
                      </td>
                      <td style={{ padding: '12px', fontWeight: '600' }}>{s.name}</td>
                      <td style={{ textAlign: 'center', padding: '12px', fontWeight: 'bold', fontSize: '18px', color: '#10b981' }}>{s.points}</td>
                      <td style={{ textAlign: 'center', padding: '12px', color: '#f59e0b', fontWeight: '600' }}>{s.wins}</td>
                      <td style={{ textAlign: 'center', padding: '12px', color: '#9ca3af' }}>{s.seconds}</td>
                      <td style={{ textAlign: 'center', padding: '12px', color: '#6b7280' }}>{s.thirds}</td>
                      <td style={{ padding: '12px', fontSize: '13px' }}>
                        {Object.entries(s.races || {}).map(([race, pts]) => (
                          <span key={race} style={{ 
                            marginRight: '6px', 
                            background: 'rgba(16, 185, 129, 0.2)', 
                            padding: '2px 6px', 
                            borderRadius: '4px',
                            color: '#10b981'
                          }}>{race}:+{pts}</span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Race Results */}
              {autoStandings.race_results?.length > 0 && (
                <div style={{ marginTop: '20px' }}>
                  <h4 style={{ color: '#9ca3af', marginBottom: '10px' }}>Race Results</h4>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                    {autoStandings.race_results.map((r, i) => (
                      <div key={i} style={{ 
                        background: 'rgba(0,0,0,0.3)', 
                        padding: '10px 15px', 
                        borderRadius: '8px',
                        minWidth: '140px'
                      }}>
                        <div style={{ fontWeight: 'bold', marginBottom: '5px', color: '#f59e0b' }}>Race {r.race}</div>
                        <div style={{ fontSize: '12px' }}>
                          {r.top3?.map((j, idx) => (
                            <div key={idx} style={{ color: idx === 0 ? '#f59e0b' : idx === 1 ? '#9ca3af' : '#b45309' }}>
                              {idx + 1}. {j}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Original Tracker (if no auto standings) */}
          {!autoStandings && trackerData && (
            <div className="card" style={{ marginBottom: '20px' }}>
              <h3>📊 Current Standings</h3>
              <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '15px' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #374151' }}>
                    <th style={{ textAlign: 'left', padding: '12px', color: '#9ca3af' }}>Name</th>
                    <th style={{ textAlign: 'center', padding: '12px', color: '#9ca3af' }}>Points</th>
                    <th style={{ textAlign: 'center', padding: '12px', color: '#9ca3af' }}>Wins</th>
                    <th style={{ textAlign: 'center', padding: '12px', color: '#9ca3af' }}>AI Price</th>
                    <th style={{ textAlign: 'center', padding: '12px', color: '#9ca3af' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(trackerData.standings || []).map((s, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #374151', background: s.is_leader ? 'rgba(245, 158, 11, 0.15)' : 'transparent' }}>
                      <td style={{ padding: '12px', fontWeight: '600' }}>{s.name}</td>
                      <td style={{ textAlign: 'center', padding: '12px', fontWeight: 'bold', fontSize: '16px' }}>{s.points}</td>
                      <td style={{ textAlign: 'center', padding: '12px', color: '#10b981' }}>{s.wins}</td>
                      <td style={{ textAlign: 'center', padding: '12px', color: '#10b981' }}>${s.ai_price?.toFixed(2)}</td>
                      <td style={{ textAlign: 'center', padding: '12px' }}>
                        {s.is_leader && <span style={{ background: '#f59e0b', color: 'black', padding: '4px 10px', borderRadius: '4px', fontSize: '12px', fontWeight: 'bold' }}>🏆 LEADER</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Manual Entry */}
          {!autoStandings && trackerData && (
            <div className="card">
              <h3>🏁 Manual Entry - Race {raceInput.race_num}</h3>
              <p style={{ color: '#9ca3af', margin: '15px 0' }}>Click jockeys in order (1st, 2nd, 3rd):</p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginBottom: '15px' }}>
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
                        background: isSelected ? (position === 1 ? '#f59e0b' : position === 2 ? '#9ca3af' : '#b45309') : '#1f2937',
                        border: '1px solid #374151',
                        borderRadius: '8px',
                        color: isSelected && position <= 3 ? 'black' : 'white',
                        cursor: isSelected ? 'default' : 'pointer'
                      }}
                    >
                      {isSelected && `${position}. `}{s.name}
                    </button>
                  );
                })}
              </div>
              <button
                onClick={updateResult}
                disabled={raceInput.results.length < 3}
                style={{
                  padding: '12px 24px',
                  background: raceInput.results.length >= 3 ? '#10b981' : '#374151',
                  border: 'none', borderRadius: '8px', color: 'white',
                  cursor: raceInput.results.length >= 3 ? 'pointer' : 'not-allowed'
                }}
              >✓ Submit Race {raceInput.race_num}</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default LiveTracker;
