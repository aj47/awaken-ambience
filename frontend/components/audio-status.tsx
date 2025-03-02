'use client';

import React from 'react';
import { Mic } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';

interface AudioStatusProps {
  isAudioSending: boolean;
  isWakeWordEnabled: boolean;
  wakeWordDetected: boolean;
}

export default function AudioStatus({ isAudioSending, isWakeWordEnabled, wakeWordDetected }: AudioStatusProps) {
  return (
    <Card>
      <CardContent className="flex items-center justify-center h-24 mt-6">
        <div className="flex flex-col items-center gap-2">
          <div className="relative">
            <Mic className={`h-8 w-8 ${isAudioSending ? 'text-green-500' : 'text-blue-500'} animate-pulse`} />
            {isAudioSending && (
              <span className="absolute -top-1 -right-1 h-3 w-3 bg-green-500 rounded-full">
                <span className="absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75 animate-ping" />
              </span>
            )}
          </div>
          <div className="flex flex-col items-center gap-1">
            <p className="text-gray-600">
              {isWakeWordEnabled && !wakeWordDetected 
                ? "Listening for wake word..."
                : "Listening to conversation..."}
            </p>
            <p className="text-xs text-gray-500">
              {isWakeWordEnabled 
                ? wakeWordDetected 
                  ? "Sending audio to Gemini..." 
                  : "Waiting for wake word..."
                : isAudioSending 
                  ? "Sending audio to Gemini..." 
                  : "Audio paused"}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
