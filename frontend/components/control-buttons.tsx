'use client';

import React from 'react';
import { Mic, StopCircle, Video, Monitor } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ControlButtonsProps {
  isStreaming: boolean;
  startStream: (mode: 'audio' | 'camera' | 'screen' | 'camera-reverse') => Promise<void>;
  stopStream: () => void;
}

export default function ControlButtons({ isStreaming, startStream, stopStream }: ControlButtonsProps) {
  return (
    <div className="flex flex-wrap gap-4 justify-center">
      {!isStreaming && (
        <>
          <Button
            onClick={() => startStream('audio')}
            disabled={isStreaming}
            className="gap-2"
          >
            <Mic className="h-4 w-4" />
            Start Chatting
          </Button>

          <Button
            onClick={() => startStream('camera')}
            disabled={isStreaming}
            className="gap-2"
          >
            <Video className="h-4 w-4" />
            Start Chatting with Video
          </Button>
        
          <Button
            onClick={() => startStream('screen')}
            disabled={isStreaming}
            className="gap-2"
          >
            <Monitor className="h-4 w-4" />
            Start Chatting with Screen
          </Button>

          <Button
            onClick={() => startStream('camera-reverse')}
            disabled={isStreaming}
            className="gap-2"
          >
            <Video className="h-4 w-4" />
            Start Chatting with Rear Camera
          </Button>
        </>
      )}

      {isStreaming && (
        <Button
          onClick={stopStream}
          variant="destructive"
          className="gap-2"
        >
          <StopCircle className="h-4 w-4" />
          Stop Chat
        </Button>
      )}
    </div>
  );
}
