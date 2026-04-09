import React, { useState } from 'react';

export default function Login({ setToken }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleAuth = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      if (isRegistering) {
        const regRes = await fetch('/api/auth/register', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ username, password }),
        });

        if (!regRes.ok) {
          const errData = await regRes.json();
          throw new Error(errData.detail || 'Registration failed');
        }
      }

      // Login (happens automatically after register too)
      const formData = new URLSearchParams();
      formData.append('username', username || 'admin');
      formData.append('password', password);

      const response = await fetch('/api/auth/token', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Invalid Credentials');
      }

      const data = await response.json();
      localStorage.setItem('odyssey_token', data.access_token);
      setToken(data.access_token);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #020617 0%, #0f172a 100%)',
      fontFamily: 'system-ui, sans-serif'
    }}>
      <form onSubmit={handleAuth} style={{
        background: 'rgba(30, 41, 59, 0.7)',
        padding: '3rem',
        borderRadius: '16px',
        border: '1px solid rgba(255,255,255,0.1)',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
        width: '100%',
        maxWidth: '400px',
        textAlign: 'center'
      }}>
        <h1 style={{ color: 'white', marginBottom: '2rem', fontSize: '1.8rem', letterSpacing: '1px' }}>
          ODYSSEY <span style={{ color: '#3b82f6' }}>V2</span>
        </h1>
        
        {error && (
          <div style={{ color: '#ef4444', marginBottom: '1rem', fontSize: '0.9rem', background: 'rgba(239, 68, 68, 0.1)', padding: '0.5rem', borderRadius: '4px' }}>
            {error}
          </div>
        )}

        <input
          type="text"
          placeholder="Username (default: admin)"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          style={{
            width: '100%',
            padding: '1rem',
            marginBottom: '1rem',
            borderRadius: '8px',
            border: '1px solid rgba(255,255,255,0.2)',
            background: 'rgba(15, 23, 42, 0.5)',
            color: 'white',
            outline: 'none',
            fontSize: '1rem',
            boxSizing: 'border-box'
          }}
        />

        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          style={{
            width: '100%',
            padding: '1rem',
            marginBottom: '1.5rem',
            borderRadius: '8px',
            border: '1px solid rgba(255,255,255,0.2)',
            background: 'rgba(15, 23, 42, 0.5)',
            color: 'white',
            outline: 'none',
            fontSize: '1rem',
            boxSizing: 'border-box'
          }}
        />

        <button 
          type="submit" 
          disabled={loading}
          style={{
            width: '100%',
            padding: '1rem',
            background: '#3b82f6',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            fontWeight: 'bold',
            fontSize: '1rem',
            cursor: loading ? 'not-allowed' : 'pointer',
            transition: 'background 0.2s',
            opacity: loading ? 0.7 : 1
          }}
        >
          {loading ? 'AUTHENTICATING...' : (isRegistering ? 'REGISTER ACCOUNT' : 'SECURE LOGIN')}
        </button>

        <div 
          onClick={() => { setIsRegistering(!isRegistering); setError(''); }}
          style={{ 
            marginTop: '1.5rem', 
            color: '#94a3b8', 
            fontSize: '0.9rem', 
            cursor: 'pointer',
            textDecoration: 'underline'
           }}
        >
          {isRegistering ? 'Already have an account? Login here' : "Don't have an account? Register"}
        </div>
      </form>
    </div>
  );
}
