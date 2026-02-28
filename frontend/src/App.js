// src/App.js - Using Centralized API Service
import React, { useState, useEffect } from "react";
import Header from "./components/Header";
import PricesTab from "./components/PricesTab";
import BetTracker from "./components/BetTracker";
import HistoryTab from "./components/HistoryTab";
import CalendarTab from "./components/CalendarTab";
import LiveTracker from "./components/LiveTracker";
import LoadingShimmer from "./components/LoadingShimmer";
import "./App.css";
import "./mobile-responsive.css";
import API from "./services/api";

function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("prices");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [challengeType, setChallengeType] = useState("all");
  const [country, setCountry] = useState("ALL");
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchData = async () => {
    if (!data) {
      setLoading(true);
    } else {
      setIsRefreshing(true);
    }

    try {
      const result = await API.prices.getAIPrices();

      if (
        result.jockey_challenges?.length > 0 ||
        result.driver_challenges?.length > 0
      ) {
        setData(result);
        setLastUpdated(new Date().toLocaleTimeString());
      }

      setError(null);
    } catch (err) {
      setError("Wait, data loading!");
    }

    setLoading(false);
    setIsRefreshing(false);
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, API.config.DATA_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, []);

  const getFilteredMeetings = () => {
    if (!data) return [];

    if (challengeType === "jockey") {
      return data.jockey_challenges || [];
    } else if (challengeType === "driver") {
      return data.driver_challenges || [];
    }
    return [
      ...(data.jockey_challenges || []),
      ...(data.driver_challenges || []),
    ];
  };

  return (
    <div className="app">
      <Header
        onRefresh={fetchData}
        loading={loading}
        lastUpdated={lastUpdated}
        isRefreshing={isRefreshing}
      />

      <main className="main-content">
        {isRefreshing && (
          <div className="refreshing-banner">🔄 Updating data...</div>
        )}

        {/* Main Tabs */}
        <div className="tabs-container">
          <div className="tabs">
            <button
              onClick={() => setActiveTab("prices")}
              className={`tab ${
                activeTab === "prices" ? "active tab-green" : ""
              }`}
            >
              <span>📊</span> AI Prices
            </button>
            <button
              onClick={() => setActiveTab("live")}
              className={`tab ${
                activeTab === "live" ? "active tab-yellow" : ""
              }`}
            >
              <span>🏇🏎️</span> Live Tracker
            </button>
            <button
              onClick={() => setActiveTab("tracker")}
              className={`tab ${
                activeTab === "tracker" ? "active tab-blue" : ""
              }`}
            >
              <span>💰</span> Bet Tracker
            </button>
            <button
              onClick={() => setActiveTab("calendar")}
              className={`tab ${
                activeTab === "calendar" ? "active tab-orange" : ""
              }`}
            >
              <span>📅</span> Calendar
            </button>
            <button
              onClick={() => setActiveTab("history")}
              className={`tab ${
                activeTab === "history" ? "active tab-purple" : ""
              }`}
            >
              <span>📜</span> History
            </button>
          </div>
        </div>

        {/* Challenge Type Filter - Only on Prices Tab */}
        {activeTab === "prices" && !loading && data && (
          <div className="filter-bar">
            <div className="filter-tabs">
              <button
                onClick={() => setChallengeType("all")}
                className={`filter-tab ${
                  challengeType === "all" ? "active" : ""
                }`}
              >
                🏆 All Challenges
              </button>
              <button
                onClick={() => setChallengeType("jockey")}
                className={`filter-tab ${
                  challengeType === "jockey" ? "active" : ""
                }`}
              >
                🏇 Jockey ({data.summary?.total_jockey_meetings || 0})
              </button>
              <button
                onClick={() => setChallengeType("driver")}
                className={`filter-tab ${
                  challengeType === "driver" ? "active" : ""
                }`}
              >
                🏎️ Driver ({data.summary?.total_driver_meetings || 0})
              </button>
            </div>
            <div className="value-indicator">
              <span className="value-dot"></span>
              {data.summary?.total_value_bets || 0} Value Bets Found
            </div>
          </div>
        )}

        {/* Content */}
        <div className="content">
          {activeTab === "prices" ? (
            loading && !data ? (
              <LoadingShimmer />
            ) : error && !data ? (
              <div className="error-state">
                <span className="error-icon">⚠️</span>
                <h3>{error}</h3>
                <button onClick={fetchData} className="btn-retry">
                  Try Again
                </button>
              </div>
            ) : (
              <PricesTab
                data={data}
                meetings={getFilteredMeetings()}
                challengeType={challengeType}
                country={country}
                setCountry={setCountry}
              />
            )
          ) : activeTab === "live" ? (
            <LiveTracker
              meetings={[
                ...(data?.jockey_challenges || []),
                ...(data?.driver_challenges || []),
              ]}
            />
          ) : activeTab === "tracker" ? (
            <BetTracker />
          ) : activeTab === "calendar" ? (
            <CalendarTab />
          ) : (
            <HistoryTab />
          )}
        </div>
      </main>

      <footer className="footer">
        <p>
          🏇 AI Racing Pricing • Live data from 6 Bookmakers • AU & NZ
          Challenges
        </p>
      </footer>
    </div>
  );
}

export default App;
