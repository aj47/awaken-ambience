'use client';

import React from "react";
import { Button } from "@/components/ui/button";
import MemoryPanel from "./memory-panel";
import SettingsPanel from "./settings-panel";

interface HeaderButtonsProps {
  isConnected: boolean;
  config: any; // Consider defining a proper type for config if possible
  setConfig: React.Dispatch<React.SetStateAction<any>>; // Same for setConfig
  onLogout: () => void;
  audioDevices: MediaDeviceInfo[];
  selectedAudioDeviceId: string | null;
  setSelectedAudioDeviceId: React.Dispatch<React.SetStateAction<string | null>>;
  videoDevices: MediaDeviceInfo[];
  selectedVideoDeviceId: string | null;
  setSelectedVideoDeviceId: React.Dispatch<React.SetStateAction<string | null>>;
}

export default function HeaderButtons({
  isConnected,
  config,
  setConfig,
  onLogout,
  audioDevices,
  selectedAudioDeviceId,
  setSelectedAudioDeviceId,
  videoDevices,
  selectedVideoDeviceId,
  setSelectedVideoDeviceId
}: HeaderButtonsProps) {
  return (
    <div className="flex flex-row items-center gap-2 w-full justify-end">
      <div className="flex items-center space-x-2">
        <MemoryPanel isConnected={isConnected} />
        <SettingsPanel
          config={config}
          setConfig={setConfig}
          isConnected={isConnected}
          audioDevices={audioDevices}
          selectedAudioDeviceId={selectedAudioDeviceId}
          setSelectedAudioDeviceId={setSelectedAudioDeviceId}
          videoDevices={videoDevices}
          selectedVideoDeviceId={selectedVideoDeviceId}
          setSelectedVideoDeviceId={setSelectedVideoDeviceId}
        />
        <Button variant="outline" onClick={onLogout}>Logout</Button>
      </div>
    </div>
  );
}
