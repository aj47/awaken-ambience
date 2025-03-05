'use client';

import React, { useState, useEffect } from 'react';
import { Database, Trash2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';

interface Memory {
  id: number;
  content: string;
  timestamp: string;
  type: string;
}

interface MemoryPanelProps {
  isConnected: boolean;
}

export default function MemoryPanel({ isConnected }: MemoryPanelProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  
  const fetchMemories = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('authToken');
      if (!token) {
        setError('Authentication required');
        return;
      }
      
      console.log("Fetching memories with token:", token);
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/memories`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error("Memory fetch error:", response.status, errorText);
        throw new Error(`Error ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log("Fetched memories:", data);
      setMemories(data);
      setError(null);
    } catch (err) {
      console.error("Memory fetch error:", err);
      setError('Failed to load memories: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteMemory = async (id: number) => {
    try {
      const token = localStorage.getItem('authToken');
      if (!token) {
        setError('Authentication required');
        return;
      }
      
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/memories/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error("Memory delete error:", response.status, errorText);
        throw new Error(`Error ${response.status}: ${response.statusText}`);
      }
      
      await fetchMemories(); // Refresh the list
      setError(null);
    } catch (err) {
      console.error("Memory delete error:", err);
      setError('Failed to delete memory: ' + err.message);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchMemories();
    }
  }, [isOpen]);

  return (
    <div className="relative">
      <Button 
        variant="outline" 
        size="icon" 
        onClick={() => setIsOpen(!isOpen)}
        className="absolute top-0 right-12 z-10"
      >
        <Database className="h-4 w-4" />
      </Button>

      {isOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-20" onClick={() => setIsOpen(false)}>
          <Card className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[90vw] max-w-[1200px] h-[90vh] max-h-[800px] overflow-y-auto z-30" onClick={(e) => e.stopPropagation()}>
            <CardContent className="pt-6 space-y-4">
              <h2 className="text-2xl font-bold text-indigo-200">Memories</h2>
              
              {loading ? (
                <div className="flex justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-indigo-500"></div>
                </div>
              ) : error ? (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : memories.length === 0 ? (
                <div className="text-center py-8 text-gray-400">
                  No memories found
                </div>
              ) : (
                <div className="space-y-4">
                  {memories.map((memory) => (
                    <div key={memory.id} className="p-4 rounded-lg bg-gray-800/50 relative group">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={() => deleteMemory(memory.id)}
                      >
                        <Trash2 className="h-4 w-4 text-red-400" />
                      </Button>
                      <p className="text-sm text-gray-400">{new Date(memory.timestamp).toLocaleString()}</p>
                      <p className="mt-2 text-indigo-100">{memory.content}</p>
                      <p className="mt-1 text-xs text-gray-500">Type: {memory.type}</p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
