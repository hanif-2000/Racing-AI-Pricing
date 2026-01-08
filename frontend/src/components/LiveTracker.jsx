// src/components/LiveTracker.jsx - Updated with fixes
import React, { useState, useEffect } from "react";
import API from "../services/api";
import MarginSlider from "./MarginSlider";
import "./LiveTracker.css";

function LiveTracker({ meetings = [] }) {
  const [activeTrackers, setActiveTrackers] = useState({});
  const [expandedMeeting, setExpandedMeeting] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [margin, setMargin] = useState(API.config.DEFAULT_MARGIN);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Fetch all active trackers on mount
  useEffect(() => {
    fetchTrackers();
  }, []);

  // Auto-refresh expanded tracker
  useEffect(() => {
    if (!autoRefresh || !expandedMeeting) return;

    const interval = setInterval(() => {
      handleAutoUpdate(expandedMeeting);
    }, API.config.LIVE_REFRESH_INTERVAL);

    return () => clearInterval(interval);
  }, [autoRefresh, expandedMeeting]);

  const fetchTrackers = async () => {
    try {
      const data = await API.liveTracker.getTrackers();
      if (data.success) {
        setActiveTrackers(data.trackers || {});
      }
    } catch (err) {
      console.error("Failed to fetch trackers:", err);
    }
  };

  const initTracker = async (meeting, type) => {
    setLoading(true);
    setError(null);
    try {
      const data = await API.liveTracker.initTracker({
        meeting: meeting.meeting,
        type: type,
        total_races: 8,
        margin: margin,
      });

      if (data.success) {
        setActiveTrackers((prev) => ({
          ...prev,
          [meeting.meeting]: data,
        }));
        setExpandedMeeting(meeting.meeting);
      } else {
        setError(data.error || "Failed to initialize tracker");
      }
    } catch (err) {
      setError("Failed to connect to server");
    } finally {
      setLoading(false);
    }
  };

  const handleAutoUpdate = async (meetingName) => {
    if (!meetingName) return;

    try {
      const data = await API.liveTracker.autoUpdate(meetingName);

      if (data.success) {
        setActiveTrackers((prev) => ({
          ...prev,
          [meetingName]: data,
        }));
      }
    } catch (err) {
      console.error("Auto-update failed:", err);
    }
  };

  const handleMarginChange = async (newMargin) => {
    setMargin(newMargin);

    if (expandedMeeting) {
      try {
        const data = await API.liveTracker.updateMargin(
          expandedMeeting,
          newMargin
        );

        if (data.success) {
          setActiveTrackers((prev) => ({
            ...prev,
            [expandedMeeting]: data,
          }));
        }
      } catch (err) {
        console.error("Failed to update margin:", err);
      }
    }
  };

  // Toggle expand/collapse - no delete API
  const toggleMeetingView = (meetingName) => {
    if (expandedMeeting === meetingName) {
      setExpandedMeeting(null);
    } else {
      setExpandedMeeting(meetingName);
    }
  };

  // Actually delete tracker
  const deleteTracker = async (meetingName, e) => {
    e.stopPropagation(); // Prevent toggle
    
    if (!window.confirm(`Delete tracker for ${meetingName}?`)) return;
    
    try {
      await API.liveTracker.deleteTracker(meetingName);
      setActiveTrackers((prev) => {
        const updated = { ...prev };
        delete updated[meetingName];
        return updated;
      });
      if (expandedMeeting === meetingName) {
        setExpandedMeeting(null);
      }
    } catch (err) {
      console.error("Failed to delete tracker:", err);
    }
  };

  const getPointsColor = (points) => {
    if (points >= 6) return "#22c55e";
    if (points >= 3) return "#eab308";
    return "#94a3b8";
  };

  const getRankBadge = (rank) => {
    if (rank === 1) return "🥇";
    if (rank === 2) return "🥈";
    if (rank === 3) return "🥉";
    return rank;
  };

  const tracker = expandedMeeting ? activeTrackers[expandedMeeting] : null;

  return (
    <div className="live-tracker">
      <div className="tracker-header">
        <h2>🔴 Live Tracker</h2>
        <div className="auto-refresh-toggle">
          <label>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh (30s)
          </label>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          ⚠️ {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Meeting Selection */}
      <div className="meeting-selection">
        <h3>SELECT MEETING TO TRACK</h3>
        <div className="meetings-list">
          {meetings.map((meeting, idx) => {
            const isTracking = !!activeTrackers[meeting.meeting];
            const isExpanded = expandedMeeting === meeting.meeting;
            const type = meeting.type || (meeting.jockeys ? "jockey" : "driver");

            return (
              <div
                key={idx}
                className={`meeting-item ${isTracking ? "tracking" : ""} ${isExpanded ? "expanded" : ""}`}
              >
                <div className="meeting-row" onClick={() => isTracking && toggleMeetingView(meeting.meeting)}>
                  <div className="meeting-info">
                    <span className="meeting-icon">
                      {type === "jockey" ? "🏇" : "🏎️"}
                    </span>
                    <span className="meeting-name">{meeting.meeting}</span>
                    <span className="country-flag">
                      {meeting.country === "AU" ? "🇦🇺" : "🇳🇿"}
                    </span>
                  </div>
                  <div className="meeting-actions">
                    {isTracking ? (
                      <>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleMeetingView(meeting.meeting);
                          }}
                          className={`view-btn ${isExpanded ? "active" : ""}`}
                        >
                          {isExpanded ? "Hide" : "View"}
                        </button>
                        {/* <button
                          onClick={(e) => deleteTracker(meeting.meeting, e)}
                          className="delete-btn"
                          title="Delete tracker"
                        >
                          ×
                        </button> */}
                      </>
                    ) : (
                      <button
                        onClick={() => initTracker(meeting, type)}
                        disabled={loading}
                        className="track-btn"
                      >
                        {loading ? "..." : "Track"}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Active Tracker Display - Collapsible */}
      {tracker && expandedMeeting && (
        <div className="tracker-display">
          <div className="tracker-info">
            <h3>{tracker.meeting}</h3>
            <div className="race-progress">
              <span>
                Race {tracker.races_completed} / {tracker.total_races}
              </span>
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{
                    width: `${(tracker.races_completed / tracker.total_races) * 100}%`,
                  }}
                />
              </div>
            </div>
          </div>

          {/* Margin Slider */}
          <MarginSlider
            value={tracker.margin || margin}
            onChange={handleMarginChange}
          />

          {/* Leaderboard */}
          <div className="leaderboard">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>NAME</th>
                  <th>POINTS</th>
                  <th>REMAINING</th>
                  <th>START ODDS</th>
                  <th>AI PRICE</th>
                  <th>VALUE</th>
                </tr>
              </thead>
              <tbody>
                {tracker.leaderboard?.map((p, idx) => (
                  <tr key={idx} className={p.value === "YES" ? "value-bet" : ""}>
                    <td className="rank">{getRankBadge(p.rank)}</td>
                    <td className="name">{p.name}</td>
                    <td className="points" style={{ color: getPointsColor(p.points) }}>
                      {p.points}
                    </td>
                    <td className="remaining">{p.rides_remaining}</td>
                    <td className="odds">${p.starting_odds?.toFixed(2)}</td>
                    <td className="ai-price">${p.ai_price?.toFixed(2)}</td>
                    <td className={`value ${p.value === "YES" ? "yes" : "no"}`}>
                      {p.value}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Race Results - Improved UI */}
          {tracker.race_results?.length > 0 && (
            <div className="race-history">
              <h4>Race Results</h4>
              <div className="race-results-grid">
                {tracker.race_results.map((race, idx) => (
                  <div key={idx} className="race-result-card">
                    <div className="race-card-header">
                      <span className="race-num">R{race.race}</span>
                      {race.dead_heats && Object.keys(race.dead_heats).length > 0 && (
                        <span className="dead-heat-badge">DH</span>
                      )}
                    </div>
                    <div className="placings-list">
                      {race.results
                        ?.filter((r) => r.position <= 3)
                        .map((r, i) => (
                          <div key={i} className={`placing-item p${r.position}`}>
                            <span className="position-medal">
                              {r.position === 1 && "🥇"}
                              {r.position === 2 && "🥈"}
                              {r.position === 3 && "🥉"}
                            </span>
                            <span className="jockey-name">
                              {r.jockey || r.driver || r.name}
                            </span>
                          </div>
                        ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Manual Refresh Button */}
          <button
            onClick={() => handleAutoUpdate(expandedMeeting)}
            className="manual-refresh-btn"
          >
            🔄 Refresh Results
          </button>
        </div>
      )}
    </div>
  );
}

export default LiveTracker;