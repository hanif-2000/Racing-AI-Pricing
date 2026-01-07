// src/services/api.js
// Centralized API Service - All API calls managed from here


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

// const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000';

// =====================================================
// 🔧 BASE CONFIG
// =====================================================

const defaultHeaders = {
  'Content-Type': 'application/json',
};

// Generic fetch wrapper with error handling
const fetchAPI = async (endpoint, options = {}) => {
  const url = `${API_BASE_URL}${endpoint}`;
  
  try {
    const response = await fetch(url, {
      headers: defaultHeaders,
      ...options,
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error(`API Error [${endpoint}]:`, error);
    throw error;
  }
};

// =====================================================
// 📊 PRICES API
// =====================================================

export const PricesAPI = {
  // Get AI prices for all meetings
  getAIPrices: () => fetchAPI('/api/ai-prices/'),
  
  // Get prices for specific meeting
  getMeetingPrices: (meeting) => fetchAPI(`/api/prices/${encodeURIComponent(meeting)}/`),
  
  // Refresh prices (trigger new scrape)
  refreshPrices: () => fetchAPI('/api/refresh-prices/', { method: 'POST' }),
};

// =====================================================
// 📅 CALENDAR API
// =====================================================

export const CalendarAPI = {
  // Get calendar data
  getCalendar: () => fetchAPI('/api/calendar/'),
  
  // Get meetings for specific date
  getMeetingsByDate: (date) => fetchAPI(`/api/calendar/${date}/`),
};

// =====================================================
// 📜 HISTORY API
// =====================================================

export const HistoryAPI = {
  // Get history with days filter
  getHistory: (days = 30) => fetchAPI(`/api/history/?days=${days}`),
  
  // Get history for specific date
  getHistoryByDate: (date) => fetchAPI(`/api/history/${date}/`),
};

// =====================================================
// 🔴 LIVE TRACKER API
// =====================================================

export const LiveTrackerAPI = {
  // Get all active trackers
  getTrackers: () => fetchAPI('/api/live/trackers/'),
  
  // Initialize a new tracker
  initTracker: (data) => fetchAPI('/api/live/init/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  
  // Auto-update tracker
  autoUpdate: (meeting) => fetchAPI('/api/live/auto-update/', {
    method: 'POST',
    body: JSON.stringify({ meeting }),
  }),
  
  // Update margin
  updateMargin: (meeting, margin) => fetchAPI('/api/live/margin/', {
    method: 'POST',
    body: JSON.stringify({ meeting, margin }),
  }),
  
  // Add race result
  addResult: (meeting, raceData) => fetchAPI('/api/live/add-result/', {
    method: 'POST',
    body: JSON.stringify({ meeting, ...raceData }),
  }),
  
  // Delete tracker
  deleteTracker: (meeting) => fetchAPI(`/api/live/tracker/${encodeURIComponent(meeting)}/`, {
    method: 'DELETE',
  }),
};

// =====================================================
// 💰 BET TRACKER API (if backend storage needed)
// =====================================================

export const BetTrackerAPI = {
  // Get all bets
  getBets: () => fetchAPI('/api/bets/'),
  
  // Add new bet
  addBet: (bet) => fetchAPI('/api/bets/', {
    method: 'POST',
    body: JSON.stringify(bet),
  }),
  
  // Update bet result
  updateBet: (id, data) => fetchAPI(`/api/bets/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  }),
  
  // Delete bet
  deleteBet: (id) => fetchAPI(`/api/bets/${id}/`, {
    method: 'DELETE',
  }),
};

// =====================================================
// 🔧 CONFIG EXPORT
// =====================================================

export const API_CONFIG = {
  BASE_URL: API_BASE_URL,
  DEFAULT_MARGIN: 1.15,
  LIVE_REFRESH_INTERVAL: 30000, // 30 seconds
  DATA_REFRESH_INTERVAL: 60000, // 1 minute
};

// =====================================================
// 📦 DEFAULT EXPORT - All APIs
// =====================================================

const API = {
  prices: PricesAPI,
  calendar: CalendarAPI,
  history: HistoryAPI,
  liveTracker: LiveTrackerAPI,
  betTracker: BetTrackerAPI,
  config: API_CONFIG,
};

export default API;