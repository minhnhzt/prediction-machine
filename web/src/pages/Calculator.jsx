import React, { useState } from 'react';
import { api } from '../api/client';

export default function Calculator() {
  const [mode, setMode] = useState('manual');
  
  // Manual params
  const [prob, setProb] = useState(0.55);
  const [odds, setOdds] = useState(2.0);
  const [bankroll, setBankroll] = useState(() => parseFloat(localStorage.getItem('bankroll') || 1000));
  const [fractional, setFractional] = useState(0.5);

  // Result state
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const calculate = async () => {
    setLoading(true);
    try {
      const res = await api.calculateKelly({ probability: prob, odds, bankroll, fractional });
      setResult(res);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container animate-fade-in" style={{ paddingBottom: '40px' }}>
      <h1 className="text-gradient" style={{ fontSize: '2.5rem', marginBottom: '32px' }}>Kelly Calculator</h1>

      <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
        <div className="glass-card" style={{ flex: '1 1 400px', padding: '24px' }}>
          <div style={{ display: 'flex', gap: '16px', marginBottom: '24px' }}>
            <button 
              className={`btn-primary ${mode !== 'manual' ? 'text-secondary' : ''}`}
              style={{ flex: 1, background: mode === 'manual' ? undefined : 'rgba(255,255,255,0.05)' }}
              onClick={() => setMode('manual')}
            >
              Manual Input
            </button>
            <button 
              className={`btn-primary ${mode !== 'team' ? 'text-secondary' : ''}`}
              style={{ flex: 1, background: mode === 'team' ? undefined : 'rgba(255,255,255,0.05)' }}
              onClick={() => setMode('team')}
            >
              Team Matchup
            </button>
          </div>

          {mode === 'manual' ? (
            <div style={{ display: 'grid', gap: '16px' }}>
              <div>
                <label className="text-secondary" style={{ display: 'block', marginBottom: '8px' }}>Win Probability ({(prob * 100).toFixed(1)}%)</label>
                <input type="range" style={{ width: '100%' }} value={prob} onChange={e => setProb(parseFloat(e.target.value))} min="0.01" max="0.99" step="0.01" />
              </div>
              <div>
                <label className="text-secondary" style={{ display: 'block', marginBottom: '8px' }}>Decimal Odds</label>
                <input type="number" className="glass-input font-mono" style={{ width: '100%' }} value={odds} onChange={e => setOdds(parseFloat(e.target.value))} min="1.01" step="0.01" />
              </div>
              <div>
                <label className="text-secondary" style={{ display: 'block', marginBottom: '8px' }}>Bankroll ($)</label>
                <input type="number" className="glass-input font-mono" style={{ width: '100%' }} value={bankroll} onChange={e => setBankroll(parseFloat(e.target.value))} min="1" step="1" />
              </div>
              <div>
                <label className="text-secondary" style={{ display: 'block', marginBottom: '8px' }}>Kelly Fraction ({fractional})</label>
                <input type="range" style={{ width: '100%' }} value={fractional} onChange={e => setFractional(parseFloat(e.target.value))} min="0.1" max="1.0" step="0.1" />
              </div>
              <button className="btn-primary" style={{ marginTop: '16px' }} onClick={calculate} disabled={loading}>
                {loading ? 'Calculating...' : 'Calculate'}
              </button>
            </div>
          ) : (
            <div className="text-secondary" style={{ textAlign: 'center', padding: '40px 0' }}>
              Team Matchup mode coming soon. Please use manual input.
            </div>
          )}
        </div>

        <div className="glass-card" style={{ flex: '1 1 400px', padding: '24px', display: 'flex', flexDirection: 'column', justifyContent: 'center', minHeight: '300px' }}>
          {result ? (
            <div className="animate-fade-in" style={{ textAlign: 'center' }}>
              <div style={{ marginBottom: '32px' }}>
                <div className="text-secondary" style={{ fontSize: '1.25rem', marginBottom: '8px' }}>Recommended Wager</div>
                <div className={`font-mono ${result.edge > 0 ? 'text-win' : 'text-loss'}`} style={{ fontSize: '4rem', fontWeight: 700, lineHeight: 1 }}>
                  ${(result.wager_amount || 0).toFixed(2)}
                </div>
              </div>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', textAlign: 'left' }}>
                <div style={{ background: 'rgba(255,255,255,0.02)', padding: '16px', borderRadius: '8px' }}>
                  <div className="text-secondary" style={{ fontSize: '0.875rem' }}>Edge</div>
                  <div className={`font-mono ${result.edge > 0 ? 'text-win' : 'text-loss'}`} style={{ fontSize: '1.5rem', fontWeight: 600 }}>
                    {(result.edge * 100).toFixed(1)}%
                  </div>
                </div>
                <div style={{ background: 'rgba(255,255,255,0.02)', padding: '16px', borderRadius: '8px' }}>
                  <div className="text-secondary" style={{ fontSize: '0.875rem' }}>Expected Value</div>
                  <div className={`font-mono ${result.expected_value > 0 ? 'text-win' : 'text-loss'}`} style={{ fontSize: '1.5rem', fontWeight: 600 }}>
                    {result.expected_value > 0 ? '+' : ''}{(result.expected_value * 100).toFixed(1)}%
                  </div>
                </div>
                <div style={{ background: 'rgba(255,255,255,0.02)', padding: '16px', borderRadius: '8px' }}>
                  <div className="text-secondary" style={{ fontSize: '0.875rem' }}>Full Kelly</div>
                  <div className="font-mono" style={{ fontSize: '1.5rem', fontWeight: 600 }}>
                    {(result.full_kelly_fraction * 100).toFixed(1)}%
                  </div>
                </div>
                <div style={{ background: 'rgba(255,255,255,0.02)', padding: '16px', borderRadius: '8px' }}>
                  <div className="text-secondary" style={{ fontSize: '0.875rem' }}>Applied ({fractional}x)</div>
                  <div className="font-mono text-accent-primary" style={{ fontSize: '1.5rem', fontWeight: 600 }}>
                    {(result.applied_fraction * 100).toFixed(1)}%
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-secondary" style={{ textAlign: 'center' }}>
              Enter parameters and calculate to see recommendations.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
