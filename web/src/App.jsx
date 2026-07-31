import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import Dashboard from './pages/Dashboard';
import Schedule from './pages/Schedule';
import Backtest from './pages/Backtest';
import Teams from './pages/Teams';
import Calculator from './pages/Calculator';

function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/schedule" element={<Schedule />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/teams" element={<Teams />} />
          <Route path="/calculator" element={<Calculator />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

export default App;
