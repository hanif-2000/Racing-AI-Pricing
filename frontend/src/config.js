// src/config.js
// Centralized configuration - NO HARDCODED URLs!

// export const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000'; // Local default
export const API_BASE_URL =
  process.env.REACT_APP_API_URL || "https://api.jockeydriverchallenge.com"; // Production default

export const API = {
  // Main
  aiPrices: (country = "ALL", margin = 1.3) =>
    `${API_BASE_URL}/api/ai-prices/?country=${country}&margin=${margin}`,
  refresh: `${API_BASE_URL}/api/refresh/`,

  // Live Tracker
  liveTrackers: `${API_BASE_URL}/api/live-tracker/`,
  initTracker: `${API_BASE_URL}/api/live-tracker/init/`,
  updateRace: `${API_BASE_URL}/api/live-tracker/update/`,
  updateMargin: `${API_BASE_URL}/api/live-tracker/margin/`,
  autoUpdate: `${API_BASE_URL}/api/live-tracker/auto-update/`,
  liveTracker: (meeting) => `${API_BASE_URL}/api/live-tracker/${meeting}/`,
  deleteTracker: (meeting) =>
    `${API_BASE_URL}/api/live-tracker/${meeting}/delete/`,

  // Bets
  bets: `${API_BASE_URL}/api/bets/`,
  addBet: `${API_BASE_URL}/api/bets/add/`,
  updateBet: `${API_BASE_URL}/api/bets/update/`,
  deleteBet: `${API_BASE_URL}/api/bets/delete/`,
  betSummary: `${API_BASE_URL}/api/bets/summary/`,

  // Calendar & History
  calendar: `${API_BASE_URL}/api/calendar/`,
  history: (days = 30) => `${API_BASE_URL}/api/history/?days=${days}`,
  meeting: (id) => `${API_BASE_URL}/api/meeting/${id}/`,

  // Auto Results
  autoStandings: (meeting) => `${API_BASE_URL}/api/auto-standings/${meeting}/`,
  results: (meeting) => `${API_BASE_URL}/api/results/${meeting}/`,
};

export const BOOKMAKERS = [
  { key: "tab", name: "TAB", color: "#f97316" },
  { key: "sportsbet", name: "Sportsbet", color: "#22c55e" },
  { key: "pointsbet", name: "PointsBet", color: "#3b82f6" },
  { key: "tabtouch", name: "TABtouch", color: "#8b5cf6" },
  { key: "ladbrokes", name: "Ladbrokes", color: "#ef4444" },
  { key: "elitebet", name: "Elitebet", color: "#eab308" },
];

export const POINTS_SYSTEM = {
  1: 3, // 1st place
  2: 2, // 2nd place
  3: 1, // 3rd place
  // Dead heat: points are split
};

export const DEFAULT_MARGIN = 1.3; // 130%
export const MIN_MARGIN = 1.0; // 100%
export const MAX_MARGIN = 1.5; // 150%

export const REFRESH_INTERVAL = 60000; // 1 minute
export const LIVE_REFRESH_INTERVAL = 30000; // 30 seconds for live tracking
