import React, { useState } from 'react';
import { api } from '../api/client';
import { useAutoRefresh } from '../hooks/useAutoRefresh';
import TeamStatsTable from '../components/TeamStatsTable';
import LoadingSpinner from '../components/LoadingSpinner';

export default function Teams() {
  const [league, setLeague] = useState(() => localStorage.getItem('league') || 'LPL');

  React.useEffect(() => {
    const handleLeague = () => setLeague(localStorage.getItem('league') || 'LPL');
    window.addEventListener('league-changed', handleLeague);
    return () => window.removeEventListener('league-changed', handleLeague);
  }, []);

  const { data, loading, error, lastUpdated } = useAutoRefresh(() => api.getTeamStats(league), 3000, [league]);

  const handleLeagueChange = (e) => {
    const val = e.target.value;
    setLeague(val);
    localStorage.setItem('league', val);
    window.dispatchEvent(new Event('league-changed'));
  };

  return (
    <div className="container animate-fade-in" style={{ paddingBottom: '40px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '32px' }}>
        <div>
          <h1 className="text-gradient" style={{ fontSize: '2.5rem', margin: 0 }}>Team Power Rankings</h1>
          <p className="text-secondary" style={{ marginTop: '8px' }}>
            Live Elo ratings and aggregated statistics
          </p>
        </div>
        
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
          <select className="glass-select" value={league} onChange={handleLeagueChange}>
            <option value="LPL">LPL</option>
            <option value="LCK">LCK</option>
          </select>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--color-win)' }} className="animate-pulse" />
            Last updated: {lastUpdated?.toLocaleTimeString()}
          </div>
        </div>
      </div>

      {error && <div style={{ color: 'var(--color-loss)' }}>Error: {error}</div>}
      
      {loading && !data ? <LoadingSpinner /> : <TeamStatsTable teams={data?.teams} />}
    </div>
  );
}
