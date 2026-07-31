import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';

export default function Navbar() {
  const [bankroll, setBankroll] = useState(
    () => localStorage.getItem('bankroll') || '1000'
  );

  useEffect(() => {
    localStorage.setItem('bankroll', bankroll);
  }, [bankroll]);

  return (
    <nav className="glass-card" style={{
      position: 'fixed', top: 0, left: 0, right: 0, 
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '16px 32px', zIndex: 100, borderRadius: 0, borderTop: 'none', borderLeft: 'none', borderRight: 'none'
    }}>
      <div style={{ fontWeight: 700, fontSize: '1.25rem' }} className="text-gradient">
        Prediction Model
      </div>
      
      <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
        <NavLink to="/" style={({isActive}) => ({
          color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
          textDecoration: 'none',
          borderBottom: isActive ? '2px solid var(--accent-primary)' : '2px solid transparent',
          paddingBottom: '4px',
          transition: 'all 0.3s ease'
        })}>Dashboard</NavLink>
        <NavLink to="/schedule" style={({isActive}) => ({
          color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
          textDecoration: 'none',
          borderBottom: isActive ? '2px solid var(--accent-primary)' : '2px solid transparent',
          paddingBottom: '4px',
          transition: 'all 0.3s ease'
        })}>Schedule</NavLink>
        <NavLink to="/backtest" style={({isActive}) => ({
          color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
          textDecoration: 'none',
          borderBottom: isActive ? '2px solid var(--accent-primary)' : '2px solid transparent',
          paddingBottom: '4px',
          transition: 'all 0.3s ease'
        })}>Backtest</NavLink>
        <NavLink to="/teams" style={({isActive}) => ({
          color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
          textDecoration: 'none',
          borderBottom: isActive ? '2px solid var(--accent-primary)' : '2px solid transparent',
          paddingBottom: '4px',
          transition: 'all 0.3s ease'
        })}>Teams</NavLink>
        <NavLink to="/calculator" style={({isActive}) => ({
          color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
          textDecoration: 'none',
          borderBottom: isActive ? '2px solid var(--accent-primary)' : '2px solid transparent',
          paddingBottom: '4px',
          transition: 'all 0.3s ease'
        })}>Calculator</NavLink>
      </div>

      <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="text-secondary text-sm">Bankroll: $</span>
          <input 
            type="number" 
            className="glass-input font-mono" 
            value={bankroll} 
            onChange={e => setBankroll(e.target.value)}
            style={{ width: '80px', padding: '4px 8px' }}
          />
        </div>
        <select className="glass-select">
          <option value="LPL">LPL</option>
          <option value="LCK">LCK</option>
        </select>
      </div>
    </nav>
  );
}
