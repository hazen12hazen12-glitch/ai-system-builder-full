'use client';
import { useEffect, useState } from 'react';
import io from 'socket.io-client';

export default function Home() {
  const [socket, setSocket] = useState(null);
  const [events, setEvents] = useState([]);
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const url = process.env.NEXT_PUBLIC_ORCHESTRATOR_URL || 'http://localhost:3000';
    const newSocket = io(url);
    newSocket.on('agent_event', (data) => {
      setEvents(prev => [...prev, data]);
    });
    setSocket(newSocket);
    return () => newSocket.close();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      console.log(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '2rem' }}>
      <h1>AI Automation System (30+ Agents)</h1>
      <form onSubmit={handleSubmit}>
        <textarea rows={10} cols={80} value={description} onChange={e => setDescription(e.target.value)} />
        <br />
        <button type="submit" disabled={loading}>Start</button>
      </form>
      {error && <p style={{ color: 'red' }}>Error: {error}</p>}
      <div>
        <h2>Live Events</h2>
        <ul>
          {events.slice(-20).map((ev, idx) => (
            <li key={idx}>{ev.timestamp} - {ev.agent}: {ev.type}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
