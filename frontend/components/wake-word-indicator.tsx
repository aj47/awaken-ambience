'use client';

import React from 'react';
import { Card, CardContent } from '@/components/ui/card';

interface WakeWordIndicatorProps {
  wakeWordDetected: boolean;
}

export default function WakeWordIndicator({ wakeWordDetected }: WakeWordIndicatorProps) {
  if (!wakeWordDetected) return null;
  
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center gap-2 text-purple-400 font-medium">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-purple-500"></span>
          </span>
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-purple-400 to-indigo-300">
            Wake word detected! Listening to conversation...
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
