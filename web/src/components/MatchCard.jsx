import React, { useState } from 'react';
import ProbabilityBar from './ProbabilityBar';
import KellyBadge from './KellyBadge';
import OddsTable from './OddsTable';

export default function MatchCard({ match }) {
  const [expanded, setExpanded] = useState(false);

  const getStatusBadge = () => {
    if (match.status === 'completed') {
      return <span style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Completed</span>;
    }
    if (match.status === 'live') {
      return <span className="text-gradient animate-pulse" style={{ fontSize: '0.875rem', fontWeight: 600, color: '#f59e0b' }}>LIVE</span>;
    }
    return <span style={{ color: 'var(--color-win)', fontSize: '0.875rem' }}>Upcoming</span>;
  };

  return (
    <div className="glass-card animate-slide-up" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="text-secondary">{new Date(match.time || Date.now()).toLocaleString()}</span>
        {getStatusBadge()}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '1.25rem', fontWeight: 600 }}>
        <span className="text-blue">{match.blue_team || 'Blue Team'}</span>
        <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>VS</span>
        <span className="text-red">{match.red_team || 'Red Team'}</span>
      </div>

      <ProbabilityBar 
        blueProb={match.prediction?.blue_win_prob || 0.5} 
        redProb={match.prediction?.red_win_prob || 0.5} 
      />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px' }}>
        <KellyBadge kelly={match.kelly} />
        <button 
          onClick={() => setExpanded(!expanded)}
          style={{ 
            background: 'none', border: 'none', color: 'var(--accent-primary)', 
            cursor: 'pointer', fontSize: '0.875rem' 
          }}
        >
          {expanded ? 'Hide Markets' : 'Show Markets'}
        </button>
      </div>

      {expanded && match.secondary_markets && (
        <div className="animate-fade-in" style={{ marginTop: '16px', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '16px' }}>
          <OddsTable markets={match.secondary_markets} />
        </div>
      )}
    </div>
  );
}
