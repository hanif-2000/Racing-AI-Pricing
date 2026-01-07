// src/components/HistoryTab.js - Fixed Status Calculation
import React, { useState, useEffect } from 'react';
import { API } from '../config';

function HistoryTab() {
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [historyData, setHistoryData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [daysFilter, setDaysFilter] = useState(30);

  useEffect(() => {
    fetchHistory();
  }, [daysFilter]);

  const fetchHistory = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(API.history(daysFilter));
      const data = await res.json();
      if (data.success) {
        // Fix status based on date
        const fixedHistory = (data.history || []).map(meeting => ({
          ...meeting,
          status: calculateStatus(meeting.date)
        }));
        setHistoryData(fixedHistory);
      } else {
        setError(data.error || 'Failed to load history');
      }
    } catch (err) {
      console.error('History fetch error:', err);
      setError('Failed to connect to server');
    } finally {
      setLoading(false);
    }
  };

  // 🔥 Calculate correct status based on date
  const calculateStatus = (dateStr) => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    const meetingDate = new Date(dateStr);
    meetingDate.setHours(0, 0, 0, 0);
    
    if (meetingDate < today) {
      return 'completed';
    } else if (meetingDate.getTime() === today.getTime()) {
      return 'live';
    } else {
      return 'upcoming';
    }
  };

  const getDateMeetings = (date) => {
    const dateStr = date.toISOString().split('T')[0];
    return historyData.filter(m => m.date === dateStr);
  };

  const getMonthStats = () => {
    const monthMeetings = historyData.filter(m => {
      const meetDate = new Date(m.date);
      return meetDate.getMonth() === currentMonth.getMonth() && 
             meetDate.getFullYear() === currentMonth.getFullYear();
    });
    
    return {
      total: monthMeetings.length,
      completed: monthMeetings.filter(m => m.status === 'completed').length,
      auCount: monthMeetings.filter(m => m.country === 'AU').length,
      nzCount: monthMeetings.filter(m => m.country === 'NZ').length
    };
  };

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
    setSelectedDate(new Date(currentMonth.getFullYear(), currentMonth.getMonth(), day));
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

  const hasMeetings = (day) => {
    const dateStr = getDateString(day);
    return historyData.some(m => m.date === dateStr);
  };

  const getDayStatus = (day) => {
    const dateStr = getDateString(day);
    const meetings = historyData.filter(m => m.date === dateStr);
    if (meetings.length === 0) return 'none';
    return meetings.every(m => m.status === 'completed') ? 'completed' : 'partial';
  };

  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November', 'December'];
  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  const selectedDateMeetings = getDateMeetings(selectedDate);
  const monthStats = getMonthStats();

  // Get type icon
  const getTypeIcon = (type) => type === 'jockey' ? '🏇' : '🏎️';
  
  // Get country flag
  const getCountryFlag = (country) => country === 'AU' ? '🇦🇺' : '🇳🇿';

  // Get status style
  const getStatusStyle = (status) => {
    const styles = {
      completed: {
        background: 'rgba(34, 197, 94, 0.2)',
        color: '#4ade80',
        border: '1px solid rgba(34, 197, 94, 0.3)'
      },
      live: {
        background: 'rgba(239, 68, 68, 0.2)',
        color: '#f87171',
        border: '1px solid rgba(239, 68, 68, 0.3)'
      },
      upcoming: {
        background: 'rgba(59, 130, 246, 0.2)',
        color: '#60a5fa',
        border: '1px solid rgba(59, 130, 246, 0.3)'
      }
    };
    return styles[status] || styles.upcoming;
  };

  if (loading) {
    return (
      <div className="history-tab">
        <div className="loading-spinner">Loading history...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="history-tab">
        <div className="error-message">
          <p>⚠️ {error}</p>
          <button onClick={fetchHistory} className="retry-btn">Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="history-tab">
      {/* Stats Bar */}
      <div className="month-stats-bar">
        <div className="month-stat">
          <span className="stat-label">Month Meetings</span>
          <span className="stat-value">{monthStats.total}</span>
        </div>
        <div className="month-stat">
          <span className="stat-label">Completed</span>
          <span className="stat-value green">{monthStats.completed}</span>
        </div>
        <div className="month-stat">
          <span className="stat-label">🇦🇺 AU</span>
          <span className="stat-value">{monthStats.auCount}</span>
        </div>
        <div className="month-stat">
          <span className="stat-label">🇳🇿 NZ</span>
          <span className="stat-value">{monthStats.nzCount}</span>
        </div>
        <div className="month-stat">
          <select 
            value={daysFilter} 
            onChange={(e) => setDaysFilter(Number(e.target.value))}
            className="days-filter"
          >
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </div>
      </div>

      {/* Main Content */}
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
              const status = getDayStatus(day);
              
              return (
                <div
                  key={day}
                  onClick={() => selectDate(day)}
                  className={`calendar-day 
                    ${isToday(day) ? 'today' : ''} 
                    ${isSelected(day) ? 'selected' : ''}
                    ${hasMeetings(day) ? 'has-meetings' : ''}
                    ${status === 'completed' ? 'completed' : ''}
                  `}
                >
                  <span className="day-number">{day}</span>
                  {hasMeetings(day) && <span className="meeting-dot"></span>}
                </div>
              );
            })}
          </div>
        </div>

        {/* Selected Day Details */}
        <div className="selected-day-details">
          <h4>
            {selectedDate.toLocaleDateString('en-AU', { 
              weekday: 'long', 
              day: 'numeric', 
              month: 'long' 
            })}
            {isToday(selectedDate.getDate()) && 
             currentMonth.getMonth() === new Date().getMonth() && 
             currentMonth.getFullYear() === new Date().getFullYear() && (
              <span style={{
                marginLeft: '10px',
                background: '#22c55e',
                color: 'white',
                padding: '4px 10px',
                borderRadius: '6px',
                fontSize: '0.75rem'
              }}>Today</span>
            )}
          </h4>
          
          {selectedDateMeetings.length === 0 ? (
            <p className="no-meetings">No meetings on this day</p>
          ) : (
            <div className="meetings-list">
              {selectedDateMeetings.map((meeting, idx) => (
                <div key={idx} className="meeting-item">
                  <div className="meeting-info">
                    {/* Type Icon */}
                    <span style={{ fontSize: '1.3rem' }}>
                      {getTypeIcon(meeting.type)}
                    </span>
                    
                    {/* Meeting Name */}
                    <span className="meeting-name">{meeting.name}</span>
                    
                    {/* Type Badge */}
                    <span 
                      style={{
                        background: meeting.type === 'jockey' 
                          ? 'rgba(34, 197, 94, 0.15)' 
                          : 'rgba(168, 85, 247, 0.15)',
                        color: meeting.type === 'jockey' ? '#4ade80' : '#c084fc',
                        padding: '4px 10px',
                        borderRadius: '6px',
                        fontSize: '0.75rem',
                        fontWeight: '600'
                      }}
                    >
                      {meeting.type}
                    </span>
                    
                    {/* Country Flag */}
                    <span style={{ fontSize: '1.2rem' }}>
                      {getCountryFlag(meeting.country)}
                    </span>
                  </div>
                  
                  {/* Status Badge */}
                  <span 
                    style={{
                      padding: '6px 12px',
                      borderRadius: '20px',
                      fontSize: '0.7rem',
                      fontWeight: '700',
                      textTransform: 'uppercase',
                      ...getStatusStyle(meeting.status)
                    }}
                  >
                    {meeting.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default HistoryTab;