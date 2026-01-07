// src/config.js
// Centralized Configuration - All API endpoints & settings

// =====================================================
// 🔧 BASE URL - Change this for production
// =====================================================

const getBaseURL = () => {
  // Check environment variable first
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL;
  }
  
  // Production check
  if (process.env.NODE_ENV === 'production') {
    return 'https://api.jockeydriverchallenge.com';
  }
  
  // Default: Local development
  return 'http://127.0.0.1:8000';
};

export const API_BASE_URL = getBaseURL();

// =====================================================
// 📡 API ENDPOINTS
// =====================================================

export const API = {
  // ─────────────────────────────────────────────────
  // Main Prices
  // ─────────────────────────────────────────────────
  aiPrices: (country = 'ALL', margin = 1.3) => 
    `${API_BASE_URL}/api/ai-prices/?country=${country}&margin=${margin}`,
  
  refresh: `${API_BASE_URL}/api/refresh/`,

  // ─────────────────────────────────────────────────
  // Live Tracker
  // ─────────────────────────────────────────────────
  liveTrackers: `${API_BASE_URL}/api/live-tracker/`,
  initTracker: `${API_BASE_URL}/api/live-tracker/init/`,
  updateRace: `${API_BASE_URL}/api/live-tracker/update/`,
  updateMargin: `${API_BASE_URL}/api/live-tracker/margin/`,
  autoUpdate: `${API_BASE_URL}/api/live-tracker/auto-update/`,
  liveTracker: (meeting) => `${API_BASE_URL}/api/live-tracker/${encodeURIComponent(meeting)}/`,
  deleteTracker: (meeting) => `${API_BASE_URL}/api/live-tracker/${encodeURIComponent(meeting)}/delete/`,

  // ─────────────────────────────────────────────────
  // Bet Tracker
  // ─────────────────────────────────────────────────
  bets: `${API_BASE_URL}/api/bets/`,
  addBet: `${API_BASE_URL}/api/bets/add/`,
  updateBet: `${API_BASE_URL}/api/bets/update/`,
  deleteBet: `${API_BASE_URL}/api/bets/delete/`,
  betSummary: `${API_BASE_URL}/api/bets/summary/`,

  // ─────────────────────────────────────────────────
  // Calendar & History
  // ─────────────────────────────────────────────────
  calendar: `${API_BASE_URL}/api/calendar/`,
  history: (days = 30) => `${API_BASE_URL}/api/history/?days=${days}`,
  meeting: (id) => `${API_BASE_URL}/api/meeting/${encodeURIComponent(id)}/`,

  // ─────────────────────────────────────────────────
  // Auto Results & Standings
  // ─────────────────────────────────────────────────
  autoStandings: (meeting) => `${API_BASE_URL}/api/auto-standings/${encodeURIComponent(meeting)}/`,
  results: (meeting) => `${API_BASE_URL}/api/results/${encodeURIComponent(meeting)}/`,
};

// =====================================================
// 🎨 BOOKMAKERS CONFIG
// =====================================================

export const BOOKMAKERS = [
  { key: 'tab', name: 'TAB', color: '#f97316', bg: '#fff7ed' },
  { key: 'sportsbet', name: 'Sportsbet', color: '#22c55e', bg: '#f0fdf4' },
  { key: 'pointsbet', name: 'PointsBet', color: '#3b82f6', bg: '#eff6ff' },
  { key: 'tabtouch', name: 'TABtouch', color: '#8b5cf6', bg: '#faf5ff' },
  { key: 'ladbrokes', name: 'Ladbrokes', color: '#ef4444', bg: '#fef2f2' },
  { key: 'elitebet', name: 'Elitebet', color: '#eab308', bg: '#fefce8' },
];

// Helper to get bookmaker by key
export const getBookmaker = (key) => 
  BOOKMAKERS.find(b => b.key === key) || { key, name: key, color: '#6b7280', bg: '#f3f4f6' };

// =====================================================
// 🏆 POINTS SYSTEM
// =====================================================

export const POINTS_SYSTEM = {
  1: 3,  // 1st place = 3 points
  2: 2,  // 2nd place = 2 points
  3: 1,  // 3rd place = 1 point
};

// Calculate points for a position (handles dead heats)
export const calculatePoints = (position, deadHeatCount = 1) => {
  const basePoints = POINTS_SYSTEM[position] || 0;
  return deadHeatCount > 1 ? basePoints / deadHeatCount : basePoints;
};

// =====================================================
// ⚙️ MARGIN SETTINGS
// =====================================================

export const DEFAULT_MARGIN = 1.3;   // 130%
export const MIN_MARGIN = 1.0;       // 100% (fair odds)
export const MAX_MARGIN = 1.5;       // 150% (conservative)

// =====================================================
// ⏱️ TIMING SETTINGS
// =====================================================

export const REFRESH_INTERVAL = 60000;       // 1 minute - main data refresh
export const LIVE_REFRESH_INTERVAL = 30000;  // 30 seconds - live tracker
export const SCRAPE_INTERVAL = 300000;       // 5 minutes - backend scraping

// =====================================================
// 🌏 COUNTRY CONFIG
// =====================================================

export const COUNTRIES = [
  { code: 'ALL', name: 'All', flag: '🌏' },
  { code: 'AU', name: 'Australia', flag: '🇦🇺' },
  { code: 'NZ', name: 'New Zealand', flag: '🇳🇿' },
];

// =====================================================
// 🎯 VALUE BET THRESHOLDS
// =====================================================

export const VALUE_THRESHOLDS = {
  HOT: 20,    // Edge >= 20% = 🔥🔥🔥 HOT
  GOOD: 10,   // Edge >= 10% = 🔥🔥 Good
  MILD: 0,    // Edge > 0%   = 🔥 Mild Value
};

export const getValueRating = (edge) => {
  if (edge >= VALUE_THRESHOLDS.HOT) return { emoji: '🔥🔥🔥', class: 'value-hot', text: 'HOT!' };
  if (edge >= VALUE_THRESHOLDS.GOOD) return { emoji: '🔥🔥', class: 'value-good', text: 'Good' };
  if (edge > VALUE_THRESHOLDS.MILD) return { emoji: '🔥', class: 'value-mild', text: 'Value' };
  return { emoji: '', class: '', text: '' };
};

// =====================================================
// 🔧 UTILITY FUNCTIONS
// =====================================================

// Format odds display
export const formatOdds = (odds) => {
  if (!odds || odds === 0) return '—';
  return `$${Number(odds).toFixed(2)}`;
};

// Calculate edge percentage
export const calculateEdge = (bookieOdds, aiPrice) => {
  if (!bookieOdds || !aiPrice) return 0;
  return ((bookieOdds - aiPrice) / aiPrice * 100).toFixed(1);
};

// Check if value bet
export const isValueBet = (edge) => parseFloat(edge) > 0;

// =====================================================
// 📦 DEFAULT EXPORT
// =====================================================

const config = {
  API_BASE_URL,
  API,
  BOOKMAKERS,
  POINTS_SYSTEM,
  DEFAULT_MARGIN,
  MIN_MARGIN,
  MAX_MARGIN,
  REFRESH_INTERVAL,
  LIVE_REFRESH_INTERVAL,
  COUNTRIES,
  VALUE_THRESHOLDS,
  // Helpers
  getBookmaker,
  calculatePoints,
  getValueRating,
  formatOdds,
  calculateEdge,
  isValueBet,
};

export default config;