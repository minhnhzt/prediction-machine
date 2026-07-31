import React, { useState, useMemo } from 'react';

const COLUMNS = [
  { key: 'Elo', label: 'Elo', format: v => v?.toFixed(0) },
  { key: 'AvgKills', label: 'Avg Kills', format: v => v?.toFixed(1) },
  { key: 'AvgDragons', label: 'Avg Dragons', format: v => v?.toFixed(1) },
  { key: 'AvgTowers', label: 'Avg Towers', format: v => v?.toFixed(1) },
  { key: 'AvgGold', label: 'Avg Gold', format: v => v ? (v / 1000).toFixed(1) + 'k' : '' },
  { key: 'ObjCtrl', label: 'ObjCtrl', format: v => v ? (v * 100).toFixed(1) + '%' : '' },
];

export default function TeamStatsTable({ teams }) {
  const [sortConfig, setSortConfig] = useState({ key: 'Elo', direction: 'desc' });

  const sortedTeams = useMemo(() => {
    if (!teams) return [];
    const sortableTeams = [...teams];
    sortableTeams.sort((a, b) => {
      const aVal = a[sortConfig.key] ?? 0;
      const bVal = b[sortConfig.key] ?? 0;
      if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
    return sortableTeams;
  }, [teams, sortConfig]);

  const requestSort = (key) => {
    let direction = 'desc';
    if (sortConfig.key === key && sortConfig.direction === 'desc') {
      direction = 'asc';
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
            <th>#</th>
            <th onClick={() => requestSort('name')} style={{ cursor: 'pointer' }}>
              Team{getSortIndicator('name')}
            </th>
            {COLUMNS.map(col => (
              <th key={col.key} onClick={() => requestSort(col.key)} style={{ cursor: 'pointer' }}>
                {col.label}{getSortIndicator(col.key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedTeams.map((t, i) => (
            <tr key={t.id || i}>
              <td className="font-mono">{i + 1}</td>
              <td style={{ fontWeight: 600 }}>{t.name}</td>
              {COLUMNS.map(col => (
                <td key={col.key} className="font-mono">
                  {col.key === 'Elo' ? (
                    <span className="text-gradient">{col.format(t[col.key])}</span>
                  ) : (
                    col.format(t[col.key])
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
