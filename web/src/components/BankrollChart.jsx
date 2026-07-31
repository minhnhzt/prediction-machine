import React, { useState } from 'react';

export default function BankrollChart({ data }) {
  const [hoverIndex, setHoverIndex] = useState(null);

  if (!data || data.length === 0) return <div>No data available</div>;

  const width = 800;
  const height = 400;
  const padding = 40;

  const minVal = Math.min(...data.map(d => d.bankroll));
  const maxVal = Math.max(...data.map(d => d.bankroll));
  const initialBankroll = data[0].bankroll;

  // Add some buffer to Y axis
  const yMin = minVal * 0.95;
  const yMax = maxVal * 1.05;

  const xScale = (width - padding * 2) / (data.length - 1 || 1);
  const yScale = (height - padding * 2) / (yMax - yMin || 1);

  const getPoints = () => {
    return data.map((d, i) => {
      const x = padding + i * xScale;
      const y = height - padding - (d.bankroll - yMin) * yScale;
      return `${x},${y}`;
    }).join(' ');
  };

  const initialY = height - padding - (initialBankroll - yMin) * yScale;

  return (
    <div className="glass-card" style={{ padding: '20px', overflowX: 'auto' }}>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ minWidth: '600px' }}>
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map(pct => {
          const y = padding + (height - padding * 2) * pct;
          const val = yMax - (yMax - yMin) * pct;
          return (
            <g key={pct}>
              <line x1={padding} y1={y} x2={width - padding} y2={y} stroke="rgba(255,255,255,0.05)" />
              <text x={padding - 10} y={y + 4} fill="var(--text-secondary)" fontSize="12" textAnchor="end" className="font-mono">
                ${val.toFixed(0)}
              </text>
            </g>
          );
        })}

        {/* Initial Bankroll Line */}
        <line 
          x1={padding} y1={initialY} 
          x2={width - padding} y2={initialY} 
          stroke="var(--text-secondary)" 
          strokeDasharray="4 4" 
        />

        {/* The Line Chart */}
        <polyline
          fill="none"
          stroke={data[data.length - 1].bankroll >= initialBankroll ? 'var(--color-win)' : 'var(--color-loss)'}
          strokeWidth="3"
          points={getPoints()}
          style={{ transition: 'all 0.5s ease' }}
        />

        {/* Hover Interactions */}
        {data.map((d, i) => {
          const x = padding + i * xScale;
          const y = height - padding - (d.bankroll - yMin) * yScale;
          return (
            <g key={i}>
              <circle
                cx={x}
                cy={y}
                r="4"
                fill="var(--bg-primary)"
                stroke={d.bankroll >= initialBankroll ? 'var(--color-win)' : 'var(--color-loss)'}
                strokeWidth="2"
                onMouseEnter={() => setHoverIndex(i)}
                onMouseLeave={() => setHoverIndex(null)}
                style={{ cursor: 'pointer', transition: 'r 0.2s ease' }}
              />
              {hoverIndex === i && (
                <g>
                  <rect x={x - 40} y={y - 45} width="80" height="35" rx="4" fill="var(--bg-card-hover)" stroke="rgba(255,255,255,0.1)" />
                  <text x={x} y={y - 22} fill="var(--text-primary)" fontSize="14" textAnchor="middle" className="font-mono">
                    ${d.bankroll.toFixed(2)}
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
