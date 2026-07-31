import React from 'react';

export default function OddsTable({ markets }) {
  if (!markets || markets.length === 0) return null;

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="glass-table">
        <thead>
          <tr>
            <th>Market</th>
            <th>Probability</th>
            <th>Fair Odds</th>
            <th>Live Odds</th>
            <th>Edge</th>
          </tr>
        </thead>
        <tbody>
          {markets.map((m, idx) => {
            const hasEdge = m.edge > 0;
            return (
              <tr key={idx} style={{ 
                background: hasEdge ? 'rgba(16, 185, 129, 0.05)' : undefined 
              }}>
                <td>{m.name}</td>
                <td className="font-mono">{(m.probability * 100).toFixed(1)}%</td>
                <td className="font-mono">{m.fair_odds.toFixed(2)}</td>
                <td className="font-mono">{m.live_odds.toFixed(2)}</td>
                <td className="font-mono" style={{ color: hasEdge ? 'var(--color-win)' : 'var(--text-secondary)' }}>
                  {(m.edge * 100).toFixed(1)}%
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
