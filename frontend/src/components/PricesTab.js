import React from 'react';
import StatCard from './StatCard';
import MeetingCard from './MeetingCard';

function PricesTab({ data, meetings, challengeType }) {
  if (!meetings || meetings.length === 0) {
    return (
      <div className="empty-state">
        <span className="empty-icon">🏇</span>
        <h3>No {challengeType === 'driver' ? 'Driver' : challengeType === 'jockey' ? 'Jockey' : ''} Challenges Available</h3>
        <p>Check back when races are scheduled</p>
      </div>
    );
  }

  const totalParticipants = meetings.reduce((sum, m) => sum + (m.participants?.length || 0), 0);
  const valueBets = meetings.reduce((sum, m) => 
    sum + (m.participants?.filter(p => p.value === 'YES').length || 0), 0);
  const jockeyMeetings = meetings.filter(m => m.type === 'jockey').length;
  const driverMeetings = meetings.filter(m => m.type === 'driver').length;

  return (
    <div className="prices-tab">
      {/* Stats */}
      <div className="stats-grid">
        <StatCard 
          icon="🏆" 
          label="Total Meetings" 
          value={meetings.length} 
          color="green"
        />
        <StatCard 
          icon="🏇" 
          label="Jockey Challenges" 
          value={jockeyMeetings} 
          color="blue"
        />
        <StatCard 
          icon="🏎️" 
          label="Driver Challenges" 
          value={driverMeetings} 
          color="purple"
        />
        <StatCard 
          icon="✅" 
          label="Value Bets" 
          value={valueBets} 
          color="emerald"
        />
      </div>

      {/* Meetings */}
      <div className="meetings-list">
        {meetings.map((meeting, idx) => (
          <MeetingCard key={idx} meeting={meeting} />
        ))}
      </div>
    </div>
  );
}

export default PricesTab;
