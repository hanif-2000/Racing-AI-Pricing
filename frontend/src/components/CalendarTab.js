import React, { useState, useEffect } from 'react';

function CalendarTab() {
  const [calendarData, setCalendarData] = useState({});
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [loading, setLoading] = useState(true);
  const [meetingDetails, setMeetingDetails] = useState(null);

  // Fetch calendar data from API
  useEffect(() => {
    fetchCalendar();
  }, []);

  const fetchCalendar = async () => {
    try {
      setLoading(true);
      const res = await fetch('http://127.0.0.1:8000/api/calendar/');
      const data = await res.json();
      if (data.success) {
        setCalendarData(data.calendar || {});
      }
    } catch (err) {
      console.error('Calendar fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchMeetingDetail = async (meetingId) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/meeting/${meetingId}/`);
      const data = await res.json();
      if (data.success) {
        setMeetingDetails(data);
      }
    } catch (err) {
      console.error('Meeting detail error:', err);
    }
  };

  // Calendar helpers
  const getDaysInMonth = (date) => {
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    return { 
      daysInMonth: lastDay.getDate(), 
      startingDay: firstDay.getDay() 
    };
  };

  const { daysInMonth, startingDay } = getDaysInMonth(currentMonth);

  const prevMonth = () => {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1));
  };

  const nextMonth = () => {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1));
  };

  const selectDate = (day) => {
    const newDate = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), day);
    setSelectedDate(newDate);
    setMeetingDetails(null);
  };

  const isToday = (day) => {
    const today = new Date();
    return day === today.getDate() && 
           currentMonth.getMonth() === today.getMonth() && 
           currentMonth.getFullYear() === today.getFullYear();
  };

  const isSelected = (day) => {
    return day === selectedDate.getDate() && 
           currentMonth.getMonth() === selectedDate.getMonth() && 
           currentMonth.getFullYear() === selectedDate.getFullYear();
  };

  const getDateString = (day) => {
    const d = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), day);
    return d.toISOString().split('T')[0];
  };

  const getMeetingsForDay = (day) => {
    const dateStr = getDateString(day);
    return calendarData[dateStr] || [];
  };

  const hasMeetings = (day) => {
    return getMeetingsForDay(day).length > 0;
  };

  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November', 'December'];
  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  const selectedDateStr = selectedDate.toISOString().split('T')[0];
  const selectedMeetings = calendarData[selectedDateStr] || [];

  if (loading) {
    return (
      <div className="calendar-tab">
        <div className="loading-spinner">Loading calendar...</div>
      </div>
    );
  }

  return (
    <div className="calendar-tab">
      {/* Stats Bar */}
      <div className="month-stats-bar">
        <div className="month-stat">
          <span className="stat-label">Today's Meetings</span>
          <span className="stat-value">{calendarData[new Date().toISOString().split('T')[0]]?.length || 0}</span>
        </div>
        <div className="month-stat">
          <span className="stat-label">Total This Week</span>
          <span className="stat-value">{Object.values(calendarData).flat().length}</span>
        </div>
        <div className="month-stat">
          <span className="stat-label">🇦🇺 AU</span>
          <span className="stat-value">{Object.values(calendarData).flat().filter(m => m.country === 'AU').length}</span>
        </div>
        <div className="month-stat">
          <span className="stat-label">🇳🇿 NZ</span>
          <span className="stat-value green">{Object.values(calendarData).flat().filter(m => m.country === 'NZ').length}</span>
        </div>
      </div>

      <div className="history-content">
        {/* Calendar */}
        <div className="calendar-container">
          <div className="calendar-header">
            <button onClick={prevMonth} className="cal-nav-btn">◀</button>
            <h3>{monthNames[currentMonth.getMonth()]} {currentMonth.getFullYear()}</h3>
            <button onClick={nextMonth} className="cal-nav-btn">▶</button>
          </div>

          <div className="calendar-grid">
            {dayNames.map(day => (
              <div key={day} className="calendar-day-name">{day}</div>
            ))}
            
            {Array.from({ length: startingDay }).map((_, i) => (
              <div key={`empty-${i}`} className="calendar-day empty"></div>
            ))}
            
            {Array.from({ length: daysInMonth }).map((_, i) => {
              const day = i + 1;
              const meetings = getMeetingsForDay(day);
              const hasNZ = meetings.some(m => m.country === 'NZ');
              
              return (
                <div
                  key={day}
                  onClick={() => selectDate(day)}
                  className={`calendar-day 
                    ${isToday(day) ? 'today' : ''} 
                    ${isSelected(day) ? 'selected' : ''}
                    ${hasMeetings(day) ? 'has-bets' : ''}
                    ${hasNZ ? 'has-nz' : ''}
                  `}
                >
                  <span className="day-number">{day}</span>
                  {hasMeetings(day) && (
                    <span className="day-indicator" title={`${meetings.length} meeting(s)`}>
                      {meetings.length}
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          <div className="calendar-legend">
            <span className="legend-item"><span className="dot green"></span> Has NZ</span>
            <span className="legend-item"><span className="dot blue"></span> AU Only</span>
            <span className="legend-item"><span className="dot gray"></span> No Meetings</span>
          </div>
        </div>

        {/* Selected Date Details */}
        <div className="date-details">
          <div className="date-header">
            <h3>📅 {selectedDate.toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</h3>
            <button onClick={fetchCalendar} className="refresh-btn">🔄 Refresh</button>
          </div>

          {selectedMeetings.length > 0 ? (
            <>
              <div className="date-summary">
                <div className="summary-item">
                  <span>Total Meetings</span>
                  <span className="value">{selectedMeetings.length}</span>
                </div>
                <div className="summary-item">
                  <span>🏇 Jockey</span>
                  <span className="value">{selectedMeetings.filter(m => m.type === 'jockey').length}</span>
                </div>
                <div className="summary-item">
                  <span>🏎️ Driver</span>
                  <span className="value">{selectedMeetings.filter(m => m.type === 'driver').length}</span>
                </div>
                <div className="summary-item">
                  <span>🇳🇿 NZ</span>
                  <span className="value green">{selectedMeetings.filter(m => m.country === 'NZ').length}</span>
                </div>
              </div>

              <div className="date-bets-list">
                {selectedMeetings.map(meeting => (
                  <div 
                    key={meeting.id} 
                    className={`date-bet-card ${meeting.status}`}
                    onClick={() => fetchMeetingDetail(meeting.id)}
                  >
                    <div className="bet-main">
                      <span className="bet-type">{meeting.type === 'jockey' ? '🏇' : '🏎️'}</span>
                      <div className="bet-info">
                        <span className="bet-name">{meeting.name}</span>
                        <span className="bet-meeting">{meeting.type === 'jockey' ? 'Jockey Challenge' : 'Driver Challenge'}</span>
                      </div>
                    </div>
                    <div className="bet-details">
                      <span className={`country-badge ${meeting.country.toLowerCase()}`}>
                        {meeting.country === 'NZ' ? '🇳🇿' : '🇦🇺'} {meeting.country}
                      </span>
                      <span className={`status-badge ${meeting.status}`}>
                        {meeting.status === 'upcoming' ? '⏳' : meeting.status === 'live' ? '🔴' : '✅'} {meeting.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Meeting Details Modal */}
              {meetingDetails && (
                <div className="meeting-detail-card">
                  <div className="detail-header">
                    <h4>{meetingDetails.meeting?.name}</h4>
                    <button onClick={() => setMeetingDetails(null)} className="close-btn">✕</button>
                  </div>
                  <div className="detail-body">
                    <p><strong>Type:</strong> {meetingDetails.meeting?.type}</p>
                    <p><strong>Country:</strong> {meetingDetails.meeting?.country}</p>
                    <p><strong>Status:</strong> {meetingDetails.meeting?.status}</p>
                    
                    {meetingDetails.participants?.length > 0 && (
                      <>
                        <h5>Participants:</h5>
                        <ul className="participants-list">
                          {meetingDetails.participants.map((p, idx) => (
                            <li key={idx}>
                              {p.position ? `#${p.position} ` : ''}{p.name}
                              {p.final_points ? ` - ${p.final_points} pts` : ''}
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="no-bets-day">
              <span className="empty-icon">📭</span>
              <p>No meetings scheduled for this day</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default CalendarTab;
