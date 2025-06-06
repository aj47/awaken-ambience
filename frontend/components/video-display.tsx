'use client';

import React, { useRef, useEffect } from 'react';
import { Card, CardContent } from '@/components/ui/card';

interface VideoDisplayProps {
  videoRef: React.RefObject<HTMLVideoElement>;
  canvasRef: React.RefObject<HTMLCanvasElement>;
  videoSource: 'camera' | 'screen' | null;
}

export default function VideoDisplay({ videoRef, canvasRef, videoSource }: VideoDisplayProps) {
  return (
    <Card>
      <CardContent className="pt-6 space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="text-lg font-semibold bg-clip-text text-transparent bg-gradient-to-r from-purple-400 to-indigo-300">Visual Input</h2>
        </div>
        
        <div className="relative bg-indigo-950 rounded-lg overflow-hidden border border-indigo-800/50 shadow-inner">
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="w-full h-auto object-contain"
            style={{ transform: videoSource === 'camera' ? 'scaleX(-1)' : 'none' }}
          />
          <canvas
            ref={canvasRef}
            className="hidden"
            width={640}
            height={480}
          />
        </div>
      </CardContent>
    </Card>
  );
}
