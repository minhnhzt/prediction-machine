import React from 'react';

export default function LoadingSpinner() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '40px' }}>
      <div style={{
        width: '40px',
        height: '40px',
        borderRadius: '50%',
        background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
        animation: 'pulse 1s infinite'
      }} />
    </div>
  );
}

export function SkeletonCard() {
  return (
    <div className="glass-card animate-shimmer" style={{ height: '200px', width: '100%', marginBottom: '16px' }}></div>
  );
}
