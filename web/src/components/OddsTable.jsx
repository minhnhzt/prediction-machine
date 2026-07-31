import React from 'react';

export default function OddsTable({ markets, bovadaOdds }) {
  if (!markets || Object.keys(markets).length === 0) return null;

  // Build a lookup from bovada_odds for live odds matching
  const liveOddsMap = {};
  if (bovadaOdds) {
    // Handicap
    if (bovadaOdds.handicap) {
      const hc = bovadaOdds.handicap;
      if (hc.blue_price) liveOddsMap['Blue ' + (hc.blue_val > 0 ? '+' : '') + hc.blue_val] = hc.blue_price;
      if (hc.red_price) liveOddsMap['Red ' + (hc.red_val > 0 ? '+' : '') + hc.red_val] = hc.red_price;
    }
    // Total
    if (bovadaOdds.total) {
      if (bovadaOdds.total.over_price) liveOddsMap['Over 2.5'] = bovadaOdds.total.over_price;
      if (bovadaOdds.total.under_price) liveOddsMap['Under 2.5'] = bovadaOdds.total.under_price;
    }
    // Correct Score
    if (bovadaOdds.correct_score) {
      Object.entries(bovadaOdds.correct_score).forEach(([score, odds]) => {
        liveOddsMap[score] = odds;
        liveOddsMap['Score ' + score] = odds;
      });
    }
  }

  // Convert market_probs dict to array of row objects
  const rows = Object.entries(markets).map(([name, prob]) => {
    const fairOdds = prob > 0 ? 1 / prob : Infinity;
    const liveOdds = liveOddsMap[name] || null;
    const edge = liveOdds ? prob * liveOdds - 1 : null;
    return { name, prob, fairOdds, liveOdds, edge };
  });

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
          {rows.map((m, idx) => {
            const hasEdge = m.edge !== null && m.edge > 0;
            return (
              <tr key={idx} style={{ 
                background: hasEdge ? 'rgba(16, 185, 129, 0.08)' : undefined 
              }}>
                <td>{m.name}</td>
                <td className="font-mono">{(m.prob * 100).toFixed(1)}%</td>
                <td className="font-mono">{m.fairOdds.toFixed(2)}</td>
                <td className="font-mono">{m.liveOdds ? m.liveOdds.toFixed(2) : '—'}</td>
                <td className="font-mono" style={{ color: hasEdge ? 'var(--color-win)' : 'var(--text-secondary)' }}>
                  {m.edge !== null ? (m.edge * 100).toFixed(1) + '%' : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
