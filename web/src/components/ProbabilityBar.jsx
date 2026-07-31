import React from 'react';

export default function ProbabilityBar({ blueProb, redProb }) {
  const bluePercent = (blueProb * 100).toFixed(1);
  const redPercent = (redProb * 100).toFixed(1);

  return (
    <div style={{ width: '100%', margin: '8px 0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', fontSize: '0.875rem' }}>
        <span className="text-blue font-mono">{bluePercent}%</span>
        <span className="text-red font-mono">{redPercent}%</span>
      </div>
      <div style={{ 
        width: '100%', 
        height: '8px', 
        background: 'var(--bg-card)', 
        borderRadius: '4px', 
        display: 'flex', 
        overflow: 'hidden' 
      }}>
        <div style={{ 
          width: `${bluePercent}%`, 
          background: 'var(--color-blue-team)', 
          transition: 'width 1s ease-in-out' 
        }} />
        <div style={{ 
          width: `${redPercent}%`, 
          background: 'var(--color-red-team)', 
          transition: 'width 1s ease-in-out' 
        }} />
      </div>
    </div>
  );
}
