import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import PricesTab from './components/PricesTab';
import BetTracker from './components/BetTracker';
import HistoryTab from './components/HistoryTab';
import LoadingShimmer from './components/LoadingShimmer';
import './App.css';

function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('prices');
  const [lastUpdated, setLastUpdated] = useState(null);
  const [challengeType, setChallengeType] = useState('all');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchData = async () => {
    // Show shimmer only on first load (no data yet)
    if (!data) {
      setLoading(true);
    } else {
      setIsRefreshing(true);
    }
    
    try {
      const response = await fetch('https://racing-ai-pricing.onrender.com/api/ai-prices/');
      const result = await response.json();
      
      // ✅ Only update if we got actual data
      if (result.jockey_challenges?.length > 0 || result.driver_challenges?.length > 0) {
        setData(result);
        setLastUpdated(new Date().toLocaleTimeString());
      }
      // Empty response = keep old data
      
      setError(null);
    } catch (err) {
      setError('Backend not running. Start Django server first!');
    }
    
    setLoading(false);
    setIsRefreshing(false);
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, []);

  const getFilteredMeetings = () => {
    if (!data) return [];
    
    if (challengeType === 'jockey') {
      return data.jockey_challenges || [];
    } else if (challengeType === 'driver') {
      return data.driver_challenges || [];
    }
    return [...(data.jockey_challenges || []), ...(data.driver_challenges || [])];
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
        {/* Refreshing Banner */}
        {isRefreshing && (
          <div className="refreshing-banner">
            🔄 Updating data...
          </div>
        )}

        {/* Main Tabs */}
        <div className="tabs-container">
          <div className="tabs">
            <button 
              onClick={() => setActiveTab('prices')}
              className={`tab ${activeTab === 'prices' ? 'active tab-green' : ''}`}
            >
              <span>📊</span> AI Prices
            </button>
            <button 
              onClick={() => setActiveTab('tracker')}
              className={`tab ${activeTab === 'tracker' ? 'active tab-blue' : ''}`}
            >
              <span>💰</span> Bet Tracker
            </button>
            <button 
              onClick={() => setActiveTab('history')}
              className={`tab ${activeTab === 'history' ? 'active tab-purple' : ''}`}
            >
              <span>📅</span> History
            </button>
          </div>
        </div>

        {/* Challenge Type Filter */}
        {activeTab === 'prices' && !loading && data && (
          <div className="filter-bar">
            <div className="filter-tabs">
              <button 
                onClick={() => setChallengeType('all')}
                className={`filter-tab ${challengeType === 'all' ? 'active' : ''}`}
              >
                🏆 All Challenges
              </button>
              <button 
                onClick={() => setChallengeType('jockey')}
                className={`filter-tab ${challengeType === 'jockey' ? 'active' : ''}`}
              >
                🏇 Jockey ({data.summary?.total_jockey_meetings || 0})
              </button>
              <button 
                onClick={() => setChallengeType('driver')}
                className={`filter-tab ${challengeType === 'driver' ? 'active' : ''}`}
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
          {activeTab === 'prices' ? (
            loading && !data ? (
              <LoadingShimmer />
            ) : error && !data ? (
              <div className="error-state">
                <span className="error-icon">⚠️</span>
                <h3>{error}</h3>
                <p>Make sure Django backend is running on port 8000</p>
                <button onClick={fetchData} className="btn-retry">
                  Try Again
                </button>
              </div>
            ) : (
              <PricesTab 
                data={data} 
                meetings={getFilteredMeetings()} 
                challengeType={challengeType}
              />
            )
          ) : activeTab === 'tracker' ? (
            <BetTracker />
          ) : (
            <HistoryTab />
          )}
        </div>
      </main>

      <footer className="footer">
        <p>🏇 Racing AI Pricing • Live data from TAB.com.au • Jockey & Driver Challenges</p>
      </footer>
    </div>
  );
}

export default App;