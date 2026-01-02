import React from 'react';

function LoadingShimmer() {
  return (
    <div className="shimmer-container">
      {/* Stats Shimmer */}
      <div className="shimmer-stats">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="shimmer-stat-card">
            <div className="shimmer shimmer-icon"></div>
            <div className="shimmer-text">
              <div className="shimmer shimmer-label"></div>
              <div className="shimmer shimmer-value"></div>
            </div>
          </div>
        ))}
      </div>

      {/* Meeting Card Shimmer */}
      <div className="shimmer-meeting">
        <div className="shimmer-meeting-header">
          <div className="shimmer shimmer-meeting-icon"></div>
          <div className="shimmer-meeting-info">
            <div className="shimmer shimmer-title"></div>
            <div className="shimmer shimmer-subtitle"></div>
          </div>
        </div>
        
        <div className="shimmer-table">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} className="shimmer-row">
              <div className="shimmer shimmer-cell-small"></div>
              <div className="shimmer shimmer-cell-name"></div>
              <div className="shimmer shimmer-cell-odds"></div>
              <div className="shimmer shimmer-cell-odds"></div>
              <div className="shimmer shimmer-cell-edge"></div>
              <div className="shimmer shimmer-cell-action"></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default LoadingShimmer;
