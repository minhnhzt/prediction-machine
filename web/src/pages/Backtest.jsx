import React, { useState } from 'react';
import { api } from '../api/client';
import BankrollChart from '../components/BankrollChart';
import LoadingSpinner from '../components/LoadingSpinner';

export default function Backtest() {
  const [params, setParams] = useState({
    league: 'LPL',
    model: 'rf',
    matches: 50,
    fractional: 0.5
  });
  
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const runBacktest = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const bankroll = localStorage.getItem('bankroll') || 1000;
      const res = await api.getBacktest({ ...params, bankroll });
      setData(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container animate-fade-in" style={{ paddingBottom: '40px' }}>
      <h1 className="text-gradient" style={{ fontSize: '2.5rem', marginBottom: '32px' }}>Backtest Simulation</h1>

      <div className="glass-card" style={{ padding: '24px', marginBottom: '32px' }}>
        <form onSubmit={runBacktest} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px', alignItems: 'end' }}>
          <div>
            <label className="text-secondary" style={{ display: 'block', marginBottom: '8px', fontSize: '0.875rem' }}>League</label>
            <select className="glass-select" style={{ width: '100%' }} value={params.league} onChange={e => setParams({...params, league: e.target.value})}>
              <option value="LPL">LPL</option>
              <option value="LCK">LCK</option>
            </select>
          </div>
          <div>
            <label className="text-secondary" style={{ display: 'block', marginBottom: '8px', fontSize: '0.875rem' }}>Model</label>
            <select className="glass-select" style={{ width: '100%' }} value={params.model} onChange={e => setParams({...params, model: e.target.value})}>
              <option value="rf">Random Forest</option>
              <option value="xgb">XGBoost</option>
            </select>
          </div>
          <div>
            <label className="text-secondary" style={{ display: 'block', marginBottom: '8px', fontSize: '0.875rem' }}>Matches (Past)</label>
            <input type="number" className="glass-input font-mono" style={{ width: '100%' }} value={params.matches} onChange={e => setParams({...params, matches: parseInt(e.target.value)})} min="10" max="500" />
          </div>
          <div>
            <label className="text-secondary" style={{ display: 'block', marginBottom: '8px', fontSize: '0.875rem' }}>Fractional Kelly ({params.fractional})</label>
            <input type="range" style={{ width: '100%' }} value={params.fractional} onChange={e => setParams({...params, fractional: parseFloat(e.target.value)})} min="0.1" max="1.0" step="0.1" />
          </div>
          <button type="submit" className="btn-primary" disabled={loading} style={{ height: '42px' }}>
            {loading ? 'Running...' : 'Run Backtest'}
          </button>
        </form>
      </div>

      {error && <div style={{ color: 'var(--color-loss)', marginBottom: '20px' }}>Error: {error}</div>}

      {loading && <LoadingSpinner />}

      {data && !loading && (
        <div className="animate-slide-up">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px', marginBottom: '32px' }}>
            <div className="glass-card" style={{ padding: '20px' }}>
              <div className="text-secondary" style={{ fontSize: '0.875rem' }}>Final Bankroll</div>
              <div className={`font-mono ${data.summary?.roi >= 0 ? 'text-win' : 'text-loss'}`} style={{ fontSize: '2rem', fontWeight: 700 }}>
                ${data.summary?.final_bankroll?.toFixed(2)}
              </div>
            </div>
            <div className="glass-card" style={{ padding: '20px' }}>
              <div className="text-secondary" style={{ fontSize: '0.875rem' }}>ROI</div>
              <div className={`font-mono ${data.summary?.roi >= 0 ? 'text-win' : 'text-loss'}`} style={{ fontSize: '2rem', fontWeight: 700 }}>
                {(data.summary?.roi || 0).toFixed(2)}%
              </div>
            </div>
            <div className="glass-card" style={{ padding: '20px' }}>
              <div className="text-secondary" style={{ fontSize: '0.875rem' }}>Win Rate</div>
              <div className="font-mono text-blue" style={{ fontSize: '2rem', fontWeight: 700 }}>
                {(data.summary?.win_rate || 0).toFixed(1)}%
              </div>
            </div>
            <div className="glass-card" style={{ padding: '20px' }}>
              <div className="text-secondary" style={{ fontSize: '0.875rem' }}>Max Drawdown</div>
              <div className="font-mono text-loss" style={{ fontSize: '2rem', fontWeight: 700 }}>
                {(data.summary?.max_drawdown || 0).toFixed(1)}%
              </div>
            </div>
          </div>

          <h3 style={{ marginBottom: '16px' }}>Bankroll History</h3>
          <BankrollChart data={data.bankroll_history} />

          <h3 style={{ margin: '32px 0 16px 0' }}>Bet History</h3>
          <div className="glass-card" style={{ overflowX: 'auto', maxHeight: '400px', overflowY: 'auto' }}>
            <table className="glass-table">
              <thead style={{ position: 'sticky', top: 0, background: 'var(--bg-primary)' }}>
                <tr>
                  <th>Match</th>
                  <th>Bet On</th>
                  <th>Odds</th>
                  <th>Wager</th>
                  <th>Result</th>
                  <th>P/L</th>
                </tr>
              </thead>
              <tbody>
                {data.bets?.map((bet, i) => (
                  <tr key={i}>
                    <td>{bet.match}</td>
                    <td className={bet.team === bet.blue_team ? 'text-blue' : 'text-red'}>{bet.team}</td>
                    <td className="font-mono">{bet.odds}</td>
                    <td className="font-mono">${bet.wager.toFixed(2)}</td>
                    <td>
                      <span style={{ 
                        color: bet.won ? 'var(--color-win)' : 'var(--color-loss)',
                        background: bet.won ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                        padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600
                      }}>
                        {bet.won ? 'WIN' : 'LOSS'}
                      </span>
                    </td>
                    <td className="font-mono" style={{ color: bet.profit > 0 ? 'var(--color-win)' : 'var(--color-loss)' }}>
                      {bet.profit > 0 ? '+' : ''}{bet.profit.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
