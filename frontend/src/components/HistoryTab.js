// src/components/HistoryTab.js
// Fixed: Uses config.js instead of hardcoded URLs

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
        setHistoryData(data.history || []);
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

      <div className="history-content">
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

        <div className="selected-day-details">
          <h4>
            {selectedDate.toLocaleDateString('en-AU', { 
              weekday: 'long', 
              day: 'numeric', 
              month: 'long' 
            })}
          </h4>
          
          {selectedDateMeetings.length === 0 ? (
            <p className="no-meetings">No meetings on this day</p>
          ) : (
            <div className="meetings-list">
              {selectedDateMeetings.map((meeting, idx) => (
                <div key={idx} className="meeting-item">
                  <div className="meeting-info">
                    <span className="meeting-name">{meeting.name}</span>
                    <span className="meeting-type">{meeting.type}</span>
                    <span className={`meeting-country ${meeting.country.toLowerCase()}`}>
                      {meeting.country === 'AU' ? '🇦🇺' : '🇳🇿'}
                    </span>
                  </div>
                  <span className={`meeting-status ${meeting.status}`}>
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