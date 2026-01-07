// src/components/CalendarTab.js - Using Centralized API
import React, { useState, useEffect } from 'react';
import API from '../services/api';

function CalendarTab() {
  const [calendarData, setCalendarData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedDate, setSelectedDate] = useState(new Date());

  useEffect(() => {
    fetchCalendar();
  }, []);

  const fetchCalendar = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await API.calendar.getCalendar();
      if (data.success) {
        setCalendarData(data.calendar || {});
      } else {
        setError(data.error || 'Failed to load calendar');
      }
    } catch (err) {
      console.error('Calendar fetch error:', err);
      setError('Failed to connect to server');
    } finally {
      setLoading(false);
    }
  };

  const getNext7Days = () => {
    const days = [];
    const today = new Date();
    for (let i = 0; i < 7; i++) {
      const date = new Date(today);
      date.setDate(today.getDate() + i);
      days.push(date);
    }
    return days;
  };

  const formatDate = (date) => date.toISOString().split('T')[0];

  const getDayName = (date) => {
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    return days[date.getDay()];
  };

  const isToday = (date) => date.toDateString() === new Date().toDateString();

  const getMeetingsForDate = (date) => calendarData[formatDate(date)] || [];

  const days = getNext7Days();
  const selectedMeetings = getMeetingsForDate(selectedDate);

  if (loading) {
    return (
      <div className="calendar-tab">
        <div className="loading-spinner">Loading calendar...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="calendar-tab">
        <div className="error-message">
          <p>⚠️ {error}</p>
          <button onClick={fetchCalendar} className="retry-btn">Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="calendar-tab">
      <div className="week-strip">
        {days.map((date, idx) => {
          const meetings = getMeetingsForDate(date);
          const isSelected = formatDate(date) === formatDate(selectedDate);
          
          return (
            <div
              key={idx}
              onClick={() => setSelectedDate(date)}
              className={`day-card ${isToday(date) ? 'today' : ''} ${isSelected ? 'selected' : ''}`}
            >
              <span className="day-name">{getDayName(date)}</span>
              <span className="day-number">{date.getDate()}</span>
              {meetings.length > 0 && (
                <span className="meeting-count">{meetings.length}</span>
              )}
            </div>
          );
        })}
      </div>

      <div className="day-details">
        <h3>
          {selectedDate.toLocaleDateString('en-AU', { 
            weekday: 'long', 
            day: 'numeric', 
            month: 'long' 
          })}
          {isToday(selectedDate) && <span className="today-badge">Today</span>}
        </h3>

        {selectedMeetings.length === 0 ? (
          <div className="no-meetings">
            <p>No meetings scheduled</p>
          </div>
        ) : (
          <div className="meetings-grid">
            {selectedMeetings.map((meeting, idx) => (
              <div key={idx} className="meeting-card">
                <div className="meeting-header">
                  <span className="meeting-icon">
                    {meeting.type === 'jockey' ? '🏇' : '🏎️'}
                  </span>
                  <span className="meeting-name">{meeting.name}</span>
                  <span className={`country-badge ${meeting.country.toLowerCase()}`}>
                    {meeting.country === 'AU' ? '🇦🇺' : '🇳🇿'}
                  </span>
                </div>
                <div className="meeting-footer">
                  <span className="meeting-type">
                    {meeting.type === 'jockey' ? 'Jockey Challenge' : 'Driver Challenge'}
                  </span>
                  <span className={`status-badge ${meeting.status}`}>
                    {meeting.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default CalendarTab;