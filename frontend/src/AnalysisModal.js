import React, { useEffect, useState } from 'react';

export default function AnalysisModal({ symbol, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/analysis/detail/${symbol}`, {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('odyssey_token')}` }
    })
      .then(r => r.json())
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [symbol]);

  if (!symbol) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span>DEEP DIVE ANALYSIS: {symbol}</span>
          <button className="close-btn" onClick={onClose}>CLOSE [ESC]</button>
        </div>
        
        {loading ? (
          <div className="modal-body" style={{ color: '#ffb900' }}>&gt;&gt; ASSEMBLING QUANT-MACRO CORRELATION...</div>
        ) : data && !data.error ? (
          <div className="modal-body">
            <div className="analysis-summary">
              {data.summary}
            </div>
            
            <div className="analysis-grid">
              <div className="analysis-section">
                <div className="section-title">MICRO: TECHNICAL DRIVERS</div>
                <div className="section-value">{data.technical_drivers}</div>
              </div>
              
              <div className="analysis-section">
                <div className="section-title">MACRO: SENTIMENT CONTEXT</div>
                <div className="section-value">{data.sentiment_context}</div>
              </div>
            </div>

            <div style={{ marginTop: '20px' }}>
              <div className="section-title">PRIMARY SOURCES & ATTRIBUTION</div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '4px' }}>
                {data.sources.map(s => (
                  <span key={s} className="source-tag">{s.toUpperCase()}</span>
                ))}
              </div>
            </div>

            <div style={{ marginTop: '20px', borderTop: '1px solid #222', paddingTop: '10px' }}>
              <div className="section-title">CONFIDENCE CALIBRATION</div>
              <div style={{ fontSize: '24px', color: '#00ffff', fontWeight: 'bold' }}>
                {(data.confidence_score * 100).toFixed(1)}% <span style={{ fontSize: '12px', color: '#555' }}>MODEL PROBABILITY</span>
              </div>
            </div>
          </div>
        ) : (
          <div className="modal-body" style={{ color: '#ff3e3e' }}>&gt;&gt; ERROR: FAILED TO RETRIEVE ANALYSIS DATA</div>
        )}
      </div>
    </div>
  );
}
