"use client";
import { useState, useEffect } from 'react';
import GeminiPlayground from '@/components/gemini-playground';
import LoginForm from '@/components/login-form';
import { Button } from '@/components/ui/button';

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storedToken = localStorage.getItem('authToken');
    if (storedToken) {
      setToken(storedToken);
    }
    setLoading(false);
  }, []);

  const handleLogin = (token: string) => {
    localStorage.setItem('authToken', token);
    setToken(token);
  };

  const handleLogout = () => {
    // Force page reload after logout to ensure clean state
    localStorage.removeItem('authToken');
    setToken(null);
    window.location.reload();
  };

  if (loading) {
    return <div className="flex items-center justify-center h-screen">Loading...</div>;
  }

  if (!token) {
    return <LoginForm onLogin={handleLogin} />;
  }

  return (
    <div className="relative">
      <div className="absolute top-4 right-4 z-50">
        <Button variant="outline" onClick={handleLogout}>Logout</Button>
      </div>
      <GeminiPlayground />
    </div>
  );
}
