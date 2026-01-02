import React, { useState, useEffect } from 'react';
import StatCard from './StatCard';

function BetTracker() {
  const [bets, setBets] = useState(() => {
    const saved = localStorage.getItem('racingBets');
    return saved ? JSON.parse(saved) : [];
  });
  
  const [newBet, setNewBet] = useState({
    jockey: '',
    meeting: '',
    bookmaker: 'TAB',
    odds: '',
    stake: '',
    type: 'jockey'
  });

  const [filters, setFilters] = useState({
    bookmaker: 'all',
    type: 'all',
    result: 'all',
    period: 'all'
  });

  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    localStorage.setItem('racingBets', JSON.stringify(bets));
  }, [bets]);

  const addBet = () => {
    if (!newBet.jockey || !newBet.odds || !newBet.stake) return;
    
    const now = new Date();
    setBets([{
      ...newBet,
      id: Date.now(),
      result: 'pending',
      odds: parseFloat(newBet.odds),
      stake: parseFloat(newBet.stake),
      date: now.toLocaleDateString(),
      timestamp: now.getTime(),
      week: getWeekNumber(now),
      month: now.getMonth(),
      year: now.getFullYear()
    }, ...bets]);
    
    setNewBet({ jockey: '', meeting: '', bookmaker: 'TAB', odds: '', stake: '', type: 'jockey' });
    setShowForm(false);
  };

  const getWeekNumber = (date) => {
    const firstDayOfYear = new Date(date.getFullYear(), 0, 1);
    const pastDaysOfYear = (date - firstDayOfYear) / 86400000;
    return Math.ceil((pastDaysOfYear + firstDayOfYear.getDay() + 1) / 7);
  };

  const updateResult = (id, result) => {
    setBets(bets.map(b => b.id === id ? { ...b, result } : b));
  };

  const deleteBet = (id) => {
    if (window.confirm('Delete this bet?')) {
      setBets(bets.filter(b => b.id !== id));
    }
  };

  const clearAll = () => {
    if (window.confirm('Delete ALL bets? This cannot be undone!')) {
      setBets([]);
    }
  };

  const exportCSV = () => {
    const headers = ['Date', 'Type', 'Participant', 'Meeting', 'Bookmaker', 'Odds', 'Stake', 'Result', 'P&L'];
    const rows = bets.map(b => {
      const pnl = b.result === 'win' ? (b.odds - 1) * b.stake : b.result === 'loss' ? -b.stake : 0;
      return [b.date, b.type, b.jockey, b.meeting, b.bookmaker, b.odds, b.stake, b.result, pnl.toFixed(2)];
    });
    
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `racing-bets-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
  };

  // Filter bets
  const getFilteredBets = () => {
    let filtered = [...bets];
    
    if (filters.bookmaker !== 'all') {
      filtered = filtered.filter(b => b.bookmaker === filters.bookmaker);
    }
    if (filters.type !== 'all') {
      filtered = filtered.filter(b => b.type === filters.type);
    }
    if (filters.result !== 'all') {
      filtered = filtered.filter(b => b.result === filters.result);
    }
    if (filters.period !== 'all') {
      const now = new Date();
      const today = now.toLocaleDateString();
      const thisWeek = getWeekNumber(now);
      const thisMonth = now.getMonth();
      const thisYear = now.getFullYear();
      
      if (filters.period === 'today') {
        filtered = filtered.filter(b => b.date === today);
      } else if (filters.period === 'week') {
        filtered = filtered.filter(b => b.week === thisWeek && b.year === thisYear);
      } else if (filters.period === 'month') {
        filtered = filtered.filter(b => b.month === thisMonth && b.year === thisYear);
      }
    }
    
    return filtered;
  };

  const filteredBets = getFilteredBets();

  // Calculations
  const calcStats = (betsList) => {
    const totalStaked = betsList.reduce((sum, b) => sum + b.stake, 0);
    const totalReturns = betsList.filter(b => b.result === 'win').reduce((sum, b) => sum + (b.stake * b.odds), 0);
    const totalLost = betsList.filter(b => b.result === 'loss').reduce((sum, b) => sum + b.stake, 0);
    const settledBets = betsList.filter(b => b.result !== 'pending');
    const netProfit = totalReturns - settledBets.reduce((sum, b) => sum + b.stake, 0);
    const wins = betsList.filter(b => b.result === 'win').length;
    const losses = betsList.filter(b => b.result === 'loss').length;
    const pending = betsList.filter(b => b.result === 'pending').length;
    const winRate = settledBets.length > 0 ? (wins / settledBets.length * 100) : 0;
    const avgOdds = settledBets.length > 0 ? settledBets.reduce((sum, b) => sum + b.odds, 0) / settledBets.length : 0;
    const roi = totalStaked > 0 ? (netProfit / totalStaked * 100) : 0;
    
    return { totalStaked, totalReturns, totalLost, netProfit, wins, losses, pending, winRate, avgOdds, roi };
  };

  const stats = calcStats(filteredBets);
  const allStats = calcStats(bets);

  // Get unique values for filters
  const bookmakers = [...new Set(bets.map(b => b.bookmaker))];
  const meetings = [...new Set(bets.map(b => b.meeting).filter(m => m))];

  return (
    <div className="bet-tracker">
      {/* Summary Stats */}
      <div className="stats-grid stats-grid-5">
        <StatCard label="Total Staked" value={`$${stats.totalStaked.toFixed(2)}`} icon="💵" />
        <StatCard label="Returns" value={`$${stats.totalReturns.toFixed(2)}`} icon="💰" color="green" />
        <StatCard label="Net P&L" value={`${stats.netProfit >= 0 ? '+' : ''}$${stats.netProfit.toFixed(2)}`} icon={stats.netProfit >= 0 ? "🚀" : "📉"} color={stats.netProfit >= 0 ? "green" : "red"} />
        <StatCard label="Win Rate" value={`${stats.winRate.toFixed(1)}%`} icon="🎯" color="blue" />
        <StatCard label="ROI" value={`${stats.roi >= 0 ? '+' : ''}${stats.roi.toFixed(1)}%`} icon="��" color={stats.roi >= 0 ? "emerald" : "red"} />
      </div>

      {/* Period Stats */}
      <div className="period-stats">
        <PeriodStatCard title="Today" bets={bets} period="today" getWeekNumber={getWeekNumber} />
        <PeriodStatCard title="This Week" bets={bets} period="week" getWeekNumber={getWeekNumber} />
        <PeriodStatCard title="This Month" bets={bets} period="month" getWeekNumber={getWeekNumber} />
        <PeriodStatCard title="All Time" bets={bets} period="all" getWeekNumber={getWeekNumber} />
      </div>

      {/* Action Bar */}
      <div className="action-bar">
        <button onClick={() => setShowForm(!showForm)} className="btn-primary">
          {showForm ? '✕ Cancel' : '➕ Add Bet'}
        </button>
        <div className="action-right">
          <button onClick={exportCSV} className="btn-secondary" disabled={bets.length === 0}>
            📥 Export CSV
          </button>
          <button onClick={clearAll} className="btn-danger" disabled={bets.length === 0}>
            🗑️ Clear All
          </button>
        </div>
      </div>

      {/* Add Bet Form */}
      {showForm && (
        <div className="add-bet-form">
          <h3>➕ Add New Bet</h3>
          <div className="form-grid">
            <div className="form-group">
              <label>Type</label>
              <select
                value={newBet.type}
                onChange={e => setNewBet({...newBet, type: e.target.value})}
                className="form-input"
              >
                <option value="jockey">🏇 Jockey</option>
                <option value="driver">🏎️ Driver</option>
              </select>
            </div>
            <div className="form-group">
              <label>Participant</label>
              <input
                type="text"
                placeholder="Name"
                value={newBet.jockey}
                onChange={e => setNewBet({...newBet, jockey: e.target.value})}
                className="form-input"
              />
            </div>
            <div className="form-group">
              <label>Meeting</label>
              <input
                type="text"
                placeholder="Meeting"
                value={newBet.meeting}
                onChange={e => setNewBet({...newBet, meeting: e.target.value})}
                className="form-input"
              />
            </div>
            <div className="form-group">
              <label>Bookmaker</label>
              <select
                value={newBet.bookmaker}
                onChange={e => setNewBet({...newBet, bookmaker: e.target.value})}
                className="form-input"
              >
                <option value="TAB">TAB</option>
                <option value="Ladbrokes">Ladbrokes</option>
                <option value="Sportsbet">Sportsbet</option>
                <option value="PointsBet">PointsBet</option>
                <option value="TABtouch">TABtouch</option>
                <option value="Elitebet">Elitebet</option>
              </select>
            </div>
            <div className="form-group">
              <label>Odds</label>
              <input
                type="number"
                step="0.01"
                placeholder="2.50"
                value={newBet.odds}
                onChange={e => setNewBet({...newBet, odds: e.target.value})}
                className="form-input"
              />
            </div>
            <div className="form-group">
              <label>Stake ($)</label>
              <input
                type="number"
                step="0.01"
                placeholder="10.00"
                value={newBet.stake}
                onChange={e => setNewBet({...newBet, stake: e.target.value})}
                className="form-input"
              />
            </div>
          </div>
          <button onClick={addBet} className="btn-add-bet">
            ✅ Add Bet
          </button>
        </div>
      )}

      {/* Filters */}
      {bets.length > 0 && (
        <div className="filters-bar">
          <div className="filter-group">
            <label>Period</label>
            <select value={filters.period} onChange={e => setFilters({...filters, period: e.target.value})}>
              <option value="all">All Time</option>
              <option value="today">Today</option>
              <option value="week">This Week</option>
              <option value="month">This Month</option>
            </select>
          </div>
          <div className="filter-group">
            <label>Bookmaker</label>
            <select value={filters.bookmaker} onChange={e => setFilters({...filters, bookmaker: e.target.value})}>
              <option value="all">All</option>
              {bookmakers.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>
          <div className="filter-group">
            <label>Type</label>
            <select value={filters.type} onChange={e => setFilters({...filters, type: e.target.value})}>
              <option value="all">All</option>
              <option value="jockey">Jockey</option>
              <option value="driver">Driver</option>
            </select>
          </div>
          <div className="filter-group">
            <label>Result</label>
            <select value={filters.result} onChange={e => setFilters({...filters, result: e.target.value})}>
              <option value="all">All</option>
              <option value="pending">Pending</option>
              <option value="win">Won</option>
              <option value="loss">Lost</option>
            </select>
          </div>
          <button onClick={() => setFilters({ bookmaker: 'all', type: 'all', result: 'all', period: 'all' })} className="btn-clear-filters">
            Clear Filters
          </button>
        </div>
      )}

      {/* Bets List */}
      {filteredBets.length > 0 ? (
        <div className="bets-list">
          <div className="bets-header">
            <h3>📋 Bets ({filteredBets.length}{filteredBets.length !== bets.length ? ` of ${bets.length}` : ''})</h3>
            <div className="bets-summary">
              <span className="win-count">✅ {stats.wins} W</span>
              <span className="loss-count">❌ {stats.losses} L</span>
              <span className="pending-count">⏳ {stats.pending} P</span>
            </div>
          </div>
          
          <div className="bets-table-wrapper">
            <table className="bets-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Type</th>
                  <th>Participant</th>
                  <th>Meeting</th>
                  <th>Bookmaker</th>
                  <th className="center">Odds</th>
                  <th className="center">Stake</th>
                  <th className="center">Result</th>
                  <th className="center">P&L</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredBets.map(bet => {
                  const pnl = bet.result === 'win' 
                    ? (bet.odds - 1) * bet.stake 
                    : bet.result === 'loss' 
                      ? -bet.stake 
                      : 0;
                  
                  return (
                    <tr key={bet.id} className={`bet-row bet-${bet.result}`}>
                      <td className="date">{bet.date}</td>
                      <td className="type">
                        <span className={`type-badge ${bet.type}`}>
                          {bet.type === 'jockey' ? '🏇' : '🏎️'}
                        </span>
                      </td>
                      <td className="participant">{bet.jockey}</td>
                      <td className="meeting">{bet.meeting || '—'}</td>
                      <td>
                        <span className="bookmaker-badge">{bet.bookmaker}</span>
                      </td>
                      <td className="center odds">${bet.odds.toFixed(2)}</td>
                      <td className="center stake">${bet.stake.toFixed(2)}</td>
                      <td className="center">
                        <select
                          value={bet.result}
                          onChange={e => updateResult(bet.id, e.target.value)}
                          className={`result-select result-${bet.result}`}
                        >
                          <option value="pending">⏳ Pending</option>
                          <option value="win">✅ Win</option>
                          <option value="loss">❌ Loss</option>
                        </select>
                      </td>
                      <td className={`center pnl pnl-${pnl > 0 ? 'positive' : pnl < 0 ? 'negative' : 'neutral'}`}>
                        {bet.result === 'pending' ? '—' : `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`}
                      </td>
                      <td className="center">
                        <button onClick={() => deleteBet(bet.id)} className="btn-delete">🗑️</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : bets.length > 0 ? (
        <div className="empty-state">
          <span className="empty-icon">��</span>
          <h3>No bets match your filters</h3>
          <p>Try adjusting your filter criteria</p>
        </div>
      ) : (
        <div className="empty-state">
          <span className="empty-icon">📝</span>
          <h3>No bets recorded yet</h3>
          <p>Click "Add Bet" to start tracking your bets!</p>
        </div>
      )}
    </div>
  );
}

function PeriodStatCard({ title, bets, period, getWeekNumber }) {
  const now = new Date();
  const today = now.toLocaleDateString();
  const thisWeek = getWeekNumber(now);
  const thisMonth = now.getMonth();
  const thisYear = now.getFullYear();
  
  let filtered = bets;
  if (period === 'today') {
    filtered = bets.filter(b => b.date === today);
  } else if (period === 'week') {
    filtered = bets.filter(b => b.week === thisWeek && b.year === thisYear);
  } else if (period === 'month') {
    filtered = bets.filter(b => b.month === thisMonth && b.year === thisYear);
  }
  
  const settled = filtered.filter(b => b.result !== 'pending');
  const staked = settled.reduce((sum, b) => sum + b.stake, 0);
  const returns = filtered.filter(b => b.result === 'win').reduce((sum, b) => sum + (b.stake * b.odds), 0);
  const pnl = returns - staked;
  const wins = filtered.filter(b => b.result === 'win').length;
  const total = settled.length;
  
  return (
    <div className={`period-card ${pnl >= 0 ? 'positive' : 'negative'}`}>
      <h4>{title}</h4>
      <div className="period-pnl">{pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</div>
      <div className="period-details">
        <span>{wins}/{total} wins</span>
        <span>${staked.toFixed(0)} staked</span>
      </div>
    </div>
  );
}

export default BetTracker;
