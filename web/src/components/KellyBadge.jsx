import React from 'react';

export default function KellyBadge({ kelly }) {
  if (!kelly || kelly.edge <= 0) {
    return (
      <div style={{ 
        display: 'inline-block',
        padding: '4px 12px',
        borderRadius: '16px',
        background: 'rgba(107, 114, 128, 0.2)',
        color: 'var(--text-secondary)',
        fontSize: '0.875rem',
        border: '1px solid rgba(107, 114, 128, 0.3)'
      }}>
        SKIP — No Edge
      </div>
    );
  }

  return (
    <div style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '8px',
      padding: '4px 16px',
      borderRadius: '16px',
      background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(16, 185, 129, 0.1))',
      color: 'var(--color-win)',
      border: '1px solid rgba(16, 185, 129, 0.3)',
      fontWeight: 500,
      fontSize: '0.875rem'
    }}>
      <span>BET ${(kelly.wager_amount || 0).toFixed(2)}</span>
      <span style={{ opacity: 0.8 }}>(Edge: {(kelly.edge * 100).toFixed(1)}%)</span>
      {kelly.wager_pct && (
        <span style={{ 
          background: 'rgba(16, 185, 129, 0.2)', 
          padding: '2px 6px', 
          borderRadius: '4px',
          fontSize: '0.75rem' 
        }}>
          {kelly.wager_pct.toFixed(1)}% bankroll
        </span>
      )}
    </div>
  );
}
