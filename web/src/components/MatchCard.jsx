import React, { useState } from 'react';
import ProbabilityBar from './ProbabilityBar';
import KellyBadge from './KellyBadge';
import OddsTable from './OddsTable';

export default function MatchCard({ match }) {
  const [expanded, setExpanded] = useState(false);

  const status = match.state || match.status || 'unstarted';

  const getStatusBadge = () => {
    if (status === 'completed') {
      return <span style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Completed</span>;
    }
    if (status === 'inProgress' || status === 'live') {
      return <span className="text-gradient animate-pulse" style={{ fontSize: '0.875rem', fontWeight: 600, color: '#f59e0b' }}>LIVE</span>;
    }
    return <span style={{ color: 'var(--color-win)', fontSize: '0.875rem' }}>Upcoming</span>;
  };

  const blueName = match.blue || match.blue_team || 'Blue Team';
  const redName = match.red || match.red_team || 'Red Team';
  const blueProb = match.blue_prob ?? match.prediction?.blue_win_prob ?? 0.5;
  const redProb = match.red_prob ?? match.prediction?.red_win_prob ?? 0.5;

  // Format odds display
  const mlBlue = match.bovada_odds?.ml?.blue;
  const mlRed = match.bovada_odds?.ml?.red;

  return (
    <div className="glass-card animate-slide-up" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="text-secondary">{match.time_local || new Date(match.time || Date.now()).toLocaleString()}</span>
        {getStatusBadge()}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '1.25rem', fontWeight: 600 }}>
        <span className="text-blue">{blueName}</span>
        <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>VS</span>
        <span className="text-red">{redName}</span>
      </div>

      <ProbabilityBar blueProb={blueProb} redProb={redProb} />

      {/* Odds display */}
      {mlBlue && mlRed && (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
          <span className="font-mono" style={{ color: 'var(--color-blue-team)' }}>Odds: {mlBlue.toFixed(2)}</span>
          <span className="font-mono" style={{ color: 'var(--color-red-team)' }}>Odds: {mlRed.toFixed(2)}</span>
        </div>
      )}

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

      {expanded && match.market_probs && (
        <div className="animate-fade-in" style={{ marginTop: '16px', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '16px' }}>
          <OddsTable 
            markets={match.market_probs} 
            bovadaOdds={match.bovada_odds} 
            blueTeam={match.blue_odds_name || blueName}
            redTeam={match.red_odds_name || redName}
          />
        </div>
      )}
    </div>
  );
}
