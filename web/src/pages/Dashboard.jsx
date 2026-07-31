import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { useAutoRefresh } from '../hooks/useAutoRefresh';
import MatchCard from '../components/MatchCard';
import LoadingSpinner, { SkeletonCard } from '../components/LoadingSpinner';

export default function Dashboard() {
  const [bankroll, setBankroll] = useState(() => localStorage.getItem('bankroll') || '1000');
  const [league, setLeague] = useState(() => localStorage.getItem('league') || 'LPL');

  useEffect(() => {
    const handleBankroll = () => setBankroll(localStorage.getItem('bankroll') || '1000');
    const handleLeague = () => setLeague(localStorage.getItem('league') || 'LPL');
    
    window.addEventListener('bankroll-changed', handleBankroll);
    window.addEventListener('league-changed', handleLeague);
    
    return () => {
      window.removeEventListener('bankroll-changed', handleBankroll);
      window.removeEventListener('league-changed', handleLeague);
    };
  }, []);

  const { data, loading, error, lastUpdated } = useAutoRefresh(
    () => api.getSchedule(league, 'rf', parseFloat(bankroll) || 1000), 
    3000, 
    [league, bankroll]
  );

  if (loading && !data) {
    return (
      <div className="container" style={{ paddingBottom: '40px' }}>
        <h1 className="text-gradient" style={{ fontSize: '2.5rem', marginBottom: '24px' }}>Prediction Dashboard</h1>
        <div style={{ display: 'grid', gap: '24px', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))' }}>
          <SkeletonCard /><SkeletonCard /><SkeletonCard />
        </div>
      </div>
    );
  }

  if (error) {
    return <div className="container" style={{ color: 'var(--color-loss)' }}>Error: {error}</div>;
  }

  const matches = data?.predictions || [];
  const edgeMatches = matches.filter(m => m.kelly && m.kelly.edge > 0);

  return (
    <div className="container animate-fade-in" style={{ paddingBottom: '40px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '32px' }}>
        <div>
          <h1 className="text-gradient" style={{ fontSize: '2.5rem', margin: 0 }}>Prediction Dashboard</h1>
          <p className="text-secondary" style={{ marginTop: '8px' }}>
            Model: {data?.model_info?.name || 'Random Forest'} • Accuracy: {data?.model_info?.accuracy || '68%'}
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
          <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--color-win)' }} className="animate-pulse" />
          Last updated: {lastUpdated?.toLocaleTimeString()}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px', marginBottom: '32px' }}>
        <div className="glass-card" style={{ padding: '20px' }}>
          <div className="text-secondary" style={{ fontSize: '0.875rem' }}>Total Matches</div>
          <div className="font-mono text-gradient" style={{ fontSize: '2rem', fontWeight: 700 }}>{matches.length}</div>
        </div>
        <div className="glass-card" style={{ padding: '20px' }}>
          <div className="text-secondary" style={{ fontSize: '0.875rem' }}>Matches w/ Edge</div>
          <div className="font-mono text-win" style={{ fontSize: '2rem', fontWeight: 700 }}>{edgeMatches.length}</div>
        </div>
        <div className="glass-card" style={{ padding: '20px' }}>
          <div className="text-secondary" style={{ fontSize: '0.875rem' }}>Avg Edge</div>
          <div className="font-mono text-blue" style={{ fontSize: '2rem', fontWeight: 700 }}>
            {edgeMatches.length ? (edgeMatches.reduce((acc, m) => acc + m.kelly.edge, 0) / edgeMatches.length * 100).toFixed(1) : 0}%
          </div>
        </div>
      </div>

      <h2 style={{ fontSize: '1.5rem', marginBottom: '20px' }}>Actionable Predictions</h2>
      {edgeMatches.length === 0 ? (
        <div className="glass-card" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
          No matches with positive edge found.
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '24px', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))' }}>
          {edgeMatches.map((match, idx) => (
            <MatchCard key={idx} match={match} />
          ))}
        </div>
      )}
    </div>
  );
}
