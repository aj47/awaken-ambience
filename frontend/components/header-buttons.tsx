'use client';

import React from "react";
import { Button } from "@/components/ui/button";
import MemoryPanel from "./memory-panel";
import SettingsPanel from "./settings-panel";

interface HeaderButtonsProps {
  isConnected: boolean;
  config: any;
  setConfig: any;
  onLogout: () => void;
}

export default function HeaderButtons({ 
  isConnected, 
  config, 
  setConfig, 
  onLogout 
}: HeaderButtonsProps) {
  return (
    <div className="flex flex-row items-center gap-2 w-full justify-end">
      <MemoryPanel isConnected={isConnected} />
      <SettingsPanel 
        config={config}
        setConfig={setConfig}
        isConnected={isConnected}
      />
      <Button variant="outline" onClick={onLogout}>Logout</Button>
    </div>
  );
}
