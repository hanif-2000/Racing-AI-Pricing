import React from 'react';

function Header({ onRefresh, loading, lastUpdated }) {
  return (
    <header className="header">
      <div className="header-content">
        <div className="logo-section">
          <span className="logo-icon">🏇</span>
          <div className="logo-text">
            <h1>Racing AI Pricing</h1>
            <p>Jockey & Driver Challenge • AU & NZ</p>
          </div>
        </div>
        
        <div className="header-actions">
          {lastUpdated && (
            <span className="last-updated">Updated: {lastUpdated}</span>
          )}
          <button 
            onClick={onRefresh}
            disabled={loading}
            className="refresh-btn"
          >
            <span className={loading ? 'spin' : ''}>🔄</span>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>
    </header>
  );
}

export default Header;
