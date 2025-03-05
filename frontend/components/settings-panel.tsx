'use client';

import React from 'react';
import { Settings } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';

interface Config {
  systemPrompt: string;
  voice: string;
  googleSearch: boolean;
  allowInterruptions: boolean;
  isWakeWordEnabled: boolean;
  wakeWord: string;
  cancelPhrase: string;
}

interface SettingsPanelProps {
  config: Config;
  setConfig: React.Dispatch<React.SetStateAction<Config>>;
  isConnected: boolean;
}

export default function SettingsPanel({ config, setConfig, isConnected }: SettingsPanelProps): React.JSX.Element {
  const [isOpen, setIsOpen] = React.useState(false);
  const voices = ["Puck", "Charon", "Kore", "Fenrir", "Aoede"];

  return (
    <div className="relative">
      <Button 
        variant="outline" 
        size="icon" 
        onClick={() => setIsOpen(!isOpen)}
        className="absolute top-0 right-0 z-10"
      >
        <Settings className="h-4 w-4" />
      </Button>

      {isOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-20" onClick={() => setIsOpen(false)}>
          <Card className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[90vw] max-w-[1200px] h-[90vh] max-h-[800px] overflow-y-auto z-30" onClick={(e) => e.stopPropagation()}>
            <CardContent className="pt-6 space-y-4">
            <div className="space-y-2">
              <Label htmlFor="system-prompt" className="text-indigo-200">Ambience Prompt</Label>
              <Textarea
                id="system-prompt"
                value={config.systemPrompt}
                onChange={(e) => setConfig(prev => ({ ...prev, systemPrompt: e.target.value }))}
                disabled={isConnected}
                className="min-h-[100px]"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="voice-select" className="text-indigo-200">Voice</Label>
              <Select
                value={config.voice}
                onValueChange={(value) => setConfig(prev => ({ ...prev, voice: value }))}
                disabled={isConnected}
              >
                <SelectTrigger id="voice-select">
                  <SelectValue placeholder="Select a voice" />
                </SelectTrigger>
                <SelectContent>
                  {voices.map((voice) => (
                    <SelectItem key={voice} value={voice}>
                      {voice}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="google-search"
                checked={config.googleSearch}
                onCheckedChange={(checked) => 
                  setConfig(prev => ({ ...prev, googleSearch: checked as boolean }))}
                disabled={isConnected}
              />
              <Label htmlFor="google-search" className="text-indigo-200">Enable Google Search</Label>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="allow-interruptions"
                checked={config.allowInterruptions}
                onCheckedChange={(checked) =>
                  setConfig(prev => ({ ...prev, allowInterruptions: checked as boolean }))
                }
                disabled={isConnected}
              />
              <Label htmlFor="allow-interruptions" className="text-indigo-200">Allow Interruptions</Label>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="wake-word-enabled"
                checked={config.isWakeWordEnabled}
                onCheckedChange={(checked) => 
                  setConfig(prev => ({ ...prev, isWakeWordEnabled: checked as boolean }))}
                disabled={isConnected}
              />
              <Label htmlFor="wake-word-enabled" className="text-indigo-200">Enable Wake Word</Label>
            </div>

            {config.isWakeWordEnabled && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="wake-word" className="text-indigo-200">Wake Word</Label>
                  <Textarea
                    id="wake-word"
                    value={config.wakeWord}
                    onChange={(e) => setConfig(prev => ({ ...prev, wakeWord: e.target.value }))}
                    disabled={isConnected}
                    className="min-h-[40px]"
                    placeholder="Enter wake word phrase"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cancel-phrase" className="text-indigo-200">Cancel Phrase</Label>
                  <Textarea
                    id="cancel-phrase"
                    value={config.cancelPhrase}
                    onChange={(e) => setConfig(prev => ({ ...prev, cancelPhrase: e.target.value }))}
                    disabled={isConnected}
                    className="min-h-[40px]"
                    placeholder="Enter cancellation phrase"
                  />
                </div>
              </>
            )}
            </CardContent>
            
            <div className="flex justify-end gap-4 p-6 border-t">
              <Button 
                variant="secondary" 
                onClick={() => setIsOpen(false)}
              >
                Exit Without Saving
              </Button>
              <Button 
                onClick={() => {
                  // Save settings to localStorage
                  localStorage.setItem('geminiConfig', JSON.stringify(config));
                  setIsOpen(false);
                }}
                disabled={isConnected}
              >
                Save Changes
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
