const API_BASE = '/api';

export const api = {
  getSchedule: (league = 'LPL', model = 'rf', bankroll = 1000) => 
    fetch(`${API_BASE}/schedule?league=${league}&model=${model}&bankroll=${bankroll}`).then(r => r.json()),
  
  getBacktest: (params) => 
    fetch(`${API_BASE}/backtest?${new URLSearchParams(params)}`).then(r => r.json()),
  
  getTeamStats: (league = 'LPL') => 
    fetch(`${API_BASE}/teams/stats?league=${league}`).then(r => r.json()),
  
  calculateKelly: (body) => 
    fetch(`${API_BASE}/kelly/calculate`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    }).then(r => r.json()),
    
  predictHypothetical: (body) =>
    fetch(`${API_BASE}/predict/hypothetical`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    }).then(r => r.json()),
};
