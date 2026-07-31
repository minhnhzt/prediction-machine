import React, { useState, useMemo } from 'react';

export default function TeamStatsTable({ teams }) {
  const [sortConfig, setSortConfig] = useState({ key: 'elo', direction: 'desc' });

  const sortedTeams = useMemo(() => {
    if (!teams) return [];
    const sortableTeams = [...teams];
    sortableTeams.sort((a, b) => {
      if (a[sortConfig.key] < b[sortConfig.key]) {
        return sortConfig.direction === 'asc' ? -1 : 1;
      }
      if (a[sortConfig.key] > b[sortConfig.key]) {
        return sortConfig.direction === 'asc' ? 1 : -1;
      }
      return 0;
    });
    return sortableTeams;
  }, [teams, sortConfig]);

  const requestSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const getSortIndicator = (key) => {
    if (sortConfig.key === key) {
      return sortConfig.direction === 'asc' ? ' ↑' : ' ↓';
    }
    return '';
  };

  if (!teams || teams.length === 0) return <div>No teams data</div>;

  return (
    <div className="glass-card" style={{ overflowX: 'auto' }}>
      <table className="glass-table">
        <thead>
          <tr>
            <th onClick={() => requestSort('rank')}>Rank{getSortIndicator('rank')}</th>
            <th onClick={() => requestSort('name')}>Team{getSortIndicator('name')}</th>
            <th onClick={() => requestSort('elo')}>Elo{getSortIndicator('elo')}</th>
            <th onClick={() => requestSort('avg_kills')}>Avg Kills{getSortIndicator('avg_kills')}</th>
            <th onClick={() => requestSort('avg_dragons')}>Avg Dragons{getSortIndicator('avg_dragons')}</th>
            <th onClick={() => requestSort('avg_towers')}>Avg Towers{getSortIndicator('avg_towers')}</th>
            <th onClick={() => requestSort('avg_gold')}>Avg Gold{getSortIndicator('avg_gold')}</th>
            <th onClick={() => requestSort('obj_ctrl')}>ObjCtrl{getSortIndicator('obj_ctrl')}</th>
          </tr>
        </thead>
        <tbody>
          {sortedTeams.map((t, i) => (
            <tr key={i}>
              <td className="font-mono">{t.rank || i + 1}</td>
              <td style={{ fontWeight: 600 }}>{t.name}</td>
              <td className="font-mono text-gradient">{t.elo}</td>
              <td className="font-mono">{t.avg_kills}</td>
              <td className="font-mono">{t.avg_dragons}</td>
              <td className="font-mono">{t.avg_towers}</td>
              <td className="font-mono">{t.avg_gold}</td>
              <td className="font-mono">{t.obj_ctrl}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
