import React, { useState } from 'react';

function MeetingCard({ meeting }) {
  const [expanded, setExpanded] = useState(true);
  const participants = meeting.participants || [];
  const valueBets = participants.filter(p => p.value === 'YES');
  const isDriver = meeting.type === 'driver';

  return (
    <div className={`meeting-card ${isDriver ? 'driver-card' : 'jockey-card'}`}>
      <div className="meeting-header" onClick={() => setExpanded(!expanded)}>
        <div className="meeting-info">
          <span className="meeting-icon">{isDriver ? '🏎️' : '🏇'}</span>
          <div>
            <div className="meeting-title-row">
              <h2>{meeting.meeting}</h2>
              <span className={`challenge-badge ${isDriver ? 'driver' : 'jockey'}`}>
                {isDriver ? 'Driver Challenge' : 'Jockey Challenge'}
              </span>
            </div>
            <p>{participants.length} {isDriver ? 'drivers' : 'jockeys'} competing</p>
          </div>
        </div>
        
        <div className="meeting-actions">
          {valueBets.length > 0 && (
            <span className="value-badge">🔥 {valueBets.length} Value</span>
          )}
          <span className={`expand-icon ${expanded ? 'expanded' : ''}`}>▼</span>
        </div>
      </div>

      {expanded && (
        <div className="meeting-table-wrapper">
          <table className="meeting-table">
            <thead>
              <tr>
                <th>#</th>
                <th>{isDriver ? 'Driver' : 'Jockey'}</th>
                <th className="center">TAB Odds</th>
                <th className="center">AI Price</th>
                <th className="center">Fair %</th>
                <th className="center">Edge</th>
                <th className="center">Rating</th>
                <th className="center">Action</th>
              </tr>
            </thead>
            <tbody>
              {participants.map((participant, idx) => {
                const isValue = participant.value === 'YES';
                const edge = participant.edge || 0;
                const rating = isValue ? (edge > 20 ? '🔥🔥🔥' : edge > 10 ? '🔥🔥' : '🔥') : '';
                
                return (
                  <tr key={idx} className={isValue ? 'value-row' : ''}>
                    <td className="rank">{idx + 1}</td>
                    <td className="participant-name">{participant.name}</td>
                    <td className="center tab-odds">${participant.tab_odds?.toFixed(2)}</td>
                    <td className="center ai-price">${participant.ai_price?.toFixed(2)}</td>
                    <td className="center fair-prob">{participant.fair_prob}%</td>
                    <td className="center">
                      <span className={`edge-badge ${edge > 0 ? 'positive' : 'negative'}`}>
                        {edge > 0 ? '+' : ''}{edge.toFixed(1)}%
                      </span>
                    </td>
                    <td className="center rating">{rating || '—'}</td>
                    <td className="center">
                      {isValue ? (
                        <span className="action-badge value">✅ VALUE</span>
                      ) : (
                        <span className="action-badge pass">Pass</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default MeetingCard;
