'use client';

import React from 'react';
import { Card, CardContent } from '@/components/ui/card';

interface WakeWordDebugProps {
  isStreaming: boolean;
  wakeWordTranscript: string;
  wakeWord: string;
}

export default function WakeWordDebug({ isStreaming, wakeWordTranscript, wakeWord }: WakeWordDebugProps) {
  return (
    <Card>
      <CardContent className="pt-6 space-y-4">
        <h2 className="text-lg font-semibold">Wake Word Debug</h2>
        <div className="text-sm text-muted-foreground">
          <p>Listening for: <strong>{wakeWord.toLowerCase()}</strong></p>
          <p className="mt-2">Current transcript:</p>
          <div className="p-2 bg-gray-50 rounded-md min-h-[40px]">
            {isStreaming ? wakeWordTranscript : 'Start chat to begin listening...'}
          </div>
          {isStreaming && (
            <p className="text-xs text-yellow-600 mt-2">
              Note: Transcript may be limited while streaming due to browser microphone constraints
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
