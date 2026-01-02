import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import PricesTab from './components/PricesTab';
import BetTracker from './components/BetTracker';
import LoadingShimmer from './components/LoadingShimmer';
import './App.css';

function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('prices');
  const [lastUpdated, setLastUpdated] = useState(null);
  const [challengeType, setChallengeType] = useState('all');

  const fetchData = async () => {
    setLoading(true);
    try {
      const response = await fetch('http://127.0.0.1:8000/api/ai-prices/');
      const result = await response.json();
      setData(result);
      setError(null);
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (err) {
      setError('Backend not running. Start Django server first!');
    }
    setLoading(false);
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
      />

      <main className="main-content">
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
          {loading && !data ? (
            <LoadingShimmer />
          ) : error ? (
            <div className="error-state">
              <span className="error-icon">⚠️</span>
              <h3>{error}</h3>
              <p>Make sure Django backend is running on port 8000</p>
              <button onClick={fetchData} className="btn-retry">
                Try Again
              </button>
            </div>
          ) : activeTab === 'prices' ? (
            <PricesTab 
              data={data} 
              meetings={getFilteredMeetings()} 
              challengeType={challengeType}
            />
          ) : activeTab === 'tracker' ? (
            <BetTracker />
          ) : (
            <div className="empty-state">
              <span className="empty-icon">🚧</span>
              <h3>History Coming Soon</h3>
              <p>Track your past meetings and results</p>
            </div>
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
