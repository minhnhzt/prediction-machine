import React, { useState } from 'react';
import { api } from '../api/client';
import { useAutoRefresh } from '../hooks/useAutoRefresh';
import MatchCard from '../components/MatchCard';
import LoadingSpinner from '../components/LoadingSpinner';

export default function Schedule() {
  const [league, setLeague] = useState('LPL');
  const [model, setModel] = useState('rf');
  
  const { data, loading, error } = useAutoRefresh(() => api.getSchedule(league, model), 10000, [league, model]);

  return (
    <div className="container animate-fade-in" style={{ paddingBottom: '40px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <h1 className="text-gradient" style={{ fontSize: '2.5rem', margin: 0 }}>Full Schedule</h1>
        
        <div style={{ display: 'flex', gap: '16px' }}>
          <select className="glass-select" value={league} onChange={e => setLeague(e.target.value)}>
            <option value="LPL">LPL</option>
            <option value="LCK">LCK</option>
          </select>
          <select className="glass-select" value={model} onChange={e => setModel(e.target.value)}>
            <option value="rf">Random Forest</option>
            <option value="xgb">XGBoost</option>
          </select>
        </div>
      </div>

      {error && <div style={{ color: 'var(--color-loss)' }}>Error: {error}</div>}
      
      {loading && !data ? <LoadingSpinner /> : (
        <div style={{ display: 'grid', gap: '24px', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))' }}>
          {data?.predictions?.map((match, idx) => (
            <MatchCard key={idx} match={match} />
          ))}
          {!data?.predictions?.length && (
            <div className="text-secondary">No matches found.</div>
          )}
        </div>
      )}
    </div>
  );
}
