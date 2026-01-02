import React, { useState, useEffect } from 'react';

function HistoryTab() {
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [bets, setBets] = useState(() => {
    const saved = localStorage.getItem('racingBets');
    return saved ? JSON.parse(saved) : [];
  });

  // Get bets for selected date
  const getDateBets = (date) => {
    const dateStr = date.toLocaleDateString();
    return bets.filter(b => b.date === dateStr);
  };

  // Get bets for a specific month
  const getMonthStats = () => {
    const monthBets = bets.filter(b => {
      const betDate = new Date(b.timestamp);
      return betDate.getMonth() === currentMonth.getMonth() && 
             betDate.getFullYear() === currentMonth.getFullYear();
    });
    
    const settled = monthBets.filter(b => b.result !== 'pending');
    const staked = settled.reduce((sum, b) => sum + b.stake, 0);
    const returns = monthBets.filter(b => b.result === 'win').reduce((sum, b) => sum + (b.stake * b.odds), 0);
    const pnl = returns - staked;
    const wins = monthBets.filter(b => b.result === 'win').length;
    
    return { total: monthBets.length, wins, pnl, staked };
  };

  // Calendar helpers
  const getDaysInMonth = (date) => {
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDay = firstDay.getDay();
    
    return { daysInMonth, startingDay };
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

  const hasBets = (day) => {
    const date = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), day);
    return getDateBets(date).length > 0;
  };

  const getDayPnl = (day) => {
    const date = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), day);
    const dayBets = getDateBets(date);
    const settled = dayBets.filter(b => b.result !== 'pending');
    const staked = settled.reduce((sum, b) => sum + b.stake, 0);
    const returns = dayBets.filter(b => b.result === 'win').reduce((sum, b) => sum + (b.stake * b.odds), 0);
    return returns - staked;
  };

  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November', 'December'];
  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  const selectedDateBets = getDateBets(selectedDate);
  const monthStats = getMonthStats();

  // Calculate P&L for selected date bets
  const calcBetPnl = (bet) => {
    if (bet.result === 'win') return (bet.odds - 1) * bet.stake;
    if (bet.result === 'loss') return -bet.stake;
    return 0;
  };

  return (
    <div className="history-tab">
      {/* Month Stats */}
      <div className="month-stats-bar">
        <div className="month-stat">
          <span className="stat-label">Month Bets</span>
          <span className="stat-value">{monthStats.total}</span>
        </div>
        <div className="month-stat">
          <span className="stat-label">Wins</span>
          <span className="stat-value green">{monthStats.wins}</span>
        </div>
        <div className="month-stat">
          <span className="stat-label">Staked</span>
          <span className="stat-value">${monthStats.staked.toFixed(0)}</span>
        </div>
        <div className="month-stat">
          <span className="stat-label">Month P&L</span>
          <span className={`stat-value ${monthStats.pnl >= 0 ? 'green' : 'red'}`}>
            {monthStats.pnl >= 0 ? '+' : ''}${monthStats.pnl.toFixed(2)}
          </span>
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
              const dayPnl = getDayPnl(day);
              const hasBetsToday = hasBets(day);
              
              return (
                <div
                  key={day}
                  onClick={() => selectDate(day)}
                  className={`calendar-day 
                    ${isToday(day) ? 'today' : ''} 
                    ${isSelected(day) ? 'selected' : ''}
                    ${hasBetsToday ? 'has-bets' : ''}
                    ${hasBetsToday && dayPnl > 0 ? 'profit' : ''}
                    ${hasBetsToday && dayPnl < 0 ? 'loss' : ''}
                  `}
                >
                  <span className="day-number">{day}</span>
                  {hasBetsToday && (
                    <span className="day-indicator">●</span>
                  )}
                </div>
              );
            })}
          </div>

          <div className="calendar-legend">
            <span className="legend-item"><span className="dot green"></span> Profit</span>
            <span className="legend-item"><span className="dot red"></span> Loss</span>
            <span className="legend-item"><span className="dot gray"></span> Pending</span>
          </div>
        </div>

        {/* Selected Date Details */}
        <div className="date-details">
          <div className="date-header">
            <h3>📅 {selectedDate.toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</h3>
          </div>

          {selectedDateBets.length > 0 ? (
            <>
              <div className="date-summary">
                <div className="summary-item">
                  <span>Total Bets</span>
                  <span className="value">{selectedDateBets.length}</span>
                </div>
                <div className="summary-item">
                  <span>Won</span>
                  <span className="value green">{selectedDateBets.filter(b => b.result === 'win').length}</span>
                </div>
                <div className="summary-item">
                  <span>Lost</span>
                  <span className="value red">{selectedDateBets.filter(b => b.result === 'loss').length}</span>
                </div>
                <div className="summary-item">
                  <span>P&L</span>
                  <span className={`value ${selectedDateBets.reduce((sum, b) => sum + calcBetPnl(b), 0) >= 0 ? 'green' : 'red'}`}>
                    {selectedDateBets.reduce((sum, b) => sum + calcBetPnl(b), 0) >= 0 ? '+' : ''}
                    ${selectedDateBets.reduce((sum, b) => sum + calcBetPnl(b), 0).toFixed(2)}
                  </span>
                </div>
              </div>

              <div className="date-bets-list">
                {selectedDateBets.map(bet => {
                  const pnl = calcBetPnl(bet);
                  return (
                    <div key={bet.id} className={`date-bet-card ${bet.result}`}>
                      <div className="bet-main">
                        <span className="bet-type">{bet.type === 'jockey' ? '🏇' : '🏎️'}</span>
                        <div className="bet-info">
                          <span className="bet-name">{bet.jockey}</span>
                          <span className="bet-meeting">{bet.meeting || 'No meeting'}</span>
                        </div>
                      </div>
                      <div className="bet-details">
                        <span className="bet-bookmaker">{bet.bookmaker}</span>
                        <span className="bet-odds">${bet.odds.toFixed(2)}</span>
                        <span className="bet-stake">${bet.stake.toFixed(2)}</span>
                        <span className={`bet-result ${bet.result}`}>
                          {bet.result === 'win' ? '✅' : bet.result === 'loss' ? '❌' : '⏳'}
                        </span>
                        <span className={`bet-pnl ${pnl > 0 ? 'positive' : pnl < 0 ? 'negative' : ''}`}>
                          {bet.result === 'pending' ? '—' : `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <div className="no-bets-day">
              <span className="empty-icon">📭</span>
              <p>No bets recorded for this day</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default HistoryTab;
