import React, { useEffect, useRef } from 'react';
import { createChart } from 'lightweight-charts';

export default function CandlestickChart({ symbol, data }) {
  const chartContainerRef = useRef();
  const chartRef = useRef(null);
  const seriesRef = useRef(null);

  // 1. Chart Initialization and Destruction
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 400,
      layout: {
        background: { type: 'solid', color: 'transparent' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
      },
      crosshair: {
        mode: 0,
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const candlestickSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });

    chartRef.current = chart;
    seriesRef.current = candlestickSeries;

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);
    
    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [symbol]); // Only re-create on symbol change

  // 2. Data Update Logic
  const previousDataRef = useRef(false);

  // Reset the initialization flag if the symbol completely changes
  useEffect(() => {
    previousDataRef.current = false;
  }, [symbol]);

  useEffect(() => {
    if (!seriesRef.current || !data || data.length === 0) return;

    const formattedData = data.map(d => ({
      time: new Date(d.time || d.timestamp).getTime() / 1000,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    })).sort((a,b) => a.time - b.time);

    // Filter out duplicates based on time
    const uniqueData = [];
    const seen = new Set();
    for (const d of formattedData) {
      if (!seen.has(d.time)) {
        seen.add(d.time);
        uniqueData.push(d);
      }
    }

    try {
      if (!previousDataRef.current) {
        // Initial load: inject full history
        seriesRef.current.setData(uniqueData);
        previousDataRef.current = true;
      } else {
        // Real-time patch: only inject the most recent candle data to ensure 
        // buttery smooth TradingView-like animations and preserve zoom/pan state!
        const latestCandle = uniqueData[uniqueData.length - 1];
        if (latestCandle) {
            seriesRef.current.update(latestCandle);
        }
      }
    } catch (err) {
      console.warn('TradingView Chart update failed:', err);
    }
  }, [data]);

  return <div ref={chartContainerRef} style={{ width: '100%', height: '400px' }} />;
}
