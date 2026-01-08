const getBaseURL = () => {
  // if (process.env.REACT_APP_API_URL) {
  //   return process.env.REACT_APP_API_URL;
  // }
  // if (process.env.NODE_ENV === 'production') {
  //   return 'https://api.jockeydriverchallenge.com';
  // }
  return 'http://127.0.0.1:8000';
};

export const API_BASE_URL = getBaseURL();

const defaultHeaders = {
  'Content-Type': 'application/json',
};

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

export const PricesAPI = {
  getAIPrices: () => fetchAPI('/api/ai-prices/'),
  getMeetingPrices: (meeting) => fetchAPI(`/api/prices/${encodeURIComponent(meeting)}/`),
  refreshPrices: () => fetchAPI('/api/refresh/', { method: 'POST' }),
};

export const CalendarAPI = {
  getCalendar: () => fetchAPI('/api/calendar/'),
  getMeetingsByDate: (date) => fetchAPI(`/api/calendar/${date}/`),
};

export const HistoryAPI = {
  getHistory: (days = 30) => fetchAPI(`/api/history/?days=${days}`),
  getHistoryByDate: (date) => fetchAPI(`/api/history/${date}/`),
};

export const LiveTrackerAPI = {
  getTrackers: () => fetchAPI('/api/live-tracker/'),
  initTracker: (data) => fetchAPI('/api/live-tracker/init/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  autoUpdate: (meeting) => fetchAPI('/api/live-tracker/auto-update/', {
    method: 'POST',
    body: JSON.stringify({ meeting }),
  }),
  updateMargin: (meeting, margin) => fetchAPI('/api/live-tracker/margin/', {
    method: 'POST',
    body: JSON.stringify({ meeting, margin }),
  }),
  addResult: (meeting, raceData) => fetchAPI('/api/live-tracker/update/', {
    method: 'POST',
    body: JSON.stringify({ meeting, ...raceData }),
  }),
  deleteTracker: (meeting) => fetchAPI(`/api/live-tracker/${encodeURIComponent(meeting)}/delete/`, {
    method: 'POST',
  }),
};

export const BetTrackerAPI = {
  getBets: () => fetchAPI('/api/bets/'),
  addBet: (bet) => fetchAPI('/api/bets/add/', {
    method: 'POST',
    body: JSON.stringify(bet),
  }),
  updateBet: (id, data) => fetchAPI('/api/bets/update/', {
    method: 'POST',
    body: JSON.stringify({ bet_id: id, ...data }),
  }),
  deleteBet: (id) => fetchAPI('/api/bets/delete/', {
    method: 'POST',
    body: JSON.stringify({ bet_id: id }),
  }),
};

export const API_CONFIG = {
  BASE_URL: API_BASE_URL,
  DEFAULT_MARGIN: 1.15,
  LIVE_REFRESH_INTERVAL: 30000,
  DATA_REFRESH_INTERVAL: 60000,
};

const API = {
  prices: PricesAPI,
  calendar: CalendarAPI,
  history: HistoryAPI,
  liveTracker: LiveTrackerAPI,
  betTracker: BetTrackerAPI,
  config: API_CONFIG,
};

export default API;