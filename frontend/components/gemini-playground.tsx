"use client";

import React, { useState, useRef, useEffect } from "react";
import { Mic, StopCircle, Video, Monitor } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { base64ToFloat32Array, float32ToPcm16 } from "@/lib/utils";

// Import our components
import AudioStatus from "./audio-status";
import VideoDisplay from "./video-display";
import WakeWordIndicator from "./wake-word-indicator";
import WakeWordDebug from "./wake-word-debug";
import ControlButtons from "./control-buttons";
import HeaderButtons from "./header-buttons";

interface Config {
  systemPrompt: string;
  voice: string;
  googleSearch: boolean;
  allowInterruptions: boolean;
  isWakeWordEnabled: boolean;
  wakeWord: string;
  cancelPhrase: string;
}

interface GeminiPlaygroundProps {
  onLogout: () => void;
}

export default function GeminiPlayground({ onLogout }: GeminiPlaygroundProps) {
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isAudioSending, setIsAudioSending] = useState(false);
  const [config, setConfig] = useState<Config>({
    systemPrompt: "You are a friendly assistant",
    voice: "Puck",
    googleSearch: true,
    allowInterruptions: false,
    isWakeWordEnabled: false,
    wakeWord: "Ambience",
    cancelPhrase: "silence",
  });

  const [wakeWordDetected, setWakeWordDetected] = useState(false);

  // Load config from API on mount
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const token = localStorage.getItem("authToken");
        if (!token) {
          console.log("No auth token found, using default config");
          return;
        }

        const apiUrl =
          process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        const response = await fetch(`${apiUrl}/config`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          throw new Error(`Error ${response.status}: ${response.statusText}`);
        }

        const configData = await response.json();
        console.log("Loaded config from API:", configData);

        // Create a complete config object with fallbacks to default values
        const completeConfig = {
          systemPrompt:
            configData.systemPrompt || "You are a friendly assistant",
          voice: configData.voice || "Puck",
          googleSearch:
            configData.googleSearch !== undefined
              ? configData.googleSearch
              : true,
          allowInterruptions:
            configData.allowInterruptions !== undefined
              ? configData.allowInterruptions
              : false,
          isWakeWordEnabled:
            configData.isWakeWordEnabled !== undefined
              ? configData.isWakeWordEnabled
              : false,
          wakeWord: configData.wakeWord || "Ambience",
          cancelPhrase: configData.cancelPhrase || "silence",
        };

        setConfig(completeConfig);
      } catch (err) {
        console.error("Failed to load config from API:", err);
        // Use default config if API call fails
        const defaultConfig = {
          systemPrompt: "You are a friendly assistant",
          voice: "Puck",
          googleSearch: true,
          allowInterruptions: false,
          isWakeWordEnabled: false,
          wakeWord: "Ambience",
          cancelPhrase: "silence",
        };
        setConfig(defaultConfig);
      }
    };

    fetchConfig();
  }, []);

  // Send updated config to backend when it changes
  useEffect(() => {
    // Only save if the config has been initialized (not the first render)
    if (
      Object.keys(config).length > 0 &&
      isConnected &&
      wsRef.current?.readyState === WebSocket.OPEN
    ) {
      console.log("Sending updated config to backend");
      wsRef.current.send(
        JSON.stringify({
          type: "config",
          config: config,
        })
      );
    }
  }, [config, isConnected]);
  const [wakeWordTranscript, setWakeWordTranscript] = useState("");
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const lastInterruptTimeRef = useRef<number>(0);
  const lastWsConnectionAttemptRef = useRef<number>(0);
  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioInputRef = useRef<{
    source: MediaStreamAudioSourceNode;
    processor: ScriptProcessorNode;
    stream: MediaStream;
  } | null>(null);
  const wakeWordDetectedRef = useRef(false);
  const [videoEnabled, setVideoEnabled] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoStreamRef = useRef<MediaStream | null>(null);
  const videoIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const [chatMode, setChatMode] = useState<"audio" | "video" | null>(null);
  const [videoSource, setVideoSource] = useState<"camera" | "screen" | null>(
    null
  );

  const voices = ["Puck", "Charon", "Kore", "Fenrir", "Aoede"];
  const audioBufferRef = useRef<Float32Array[]>([]);
  const isPlayingRef = useRef(false);
  const currentAudioSourceRef = useRef<AudioBufferSourceNode | null>(null);

  const startStream = async (mode: "audio" | "camera" | "screen") => {
    if (mode !== "audio") {
      setChatMode("video");
    } else {
      setChatMode("audio");
    }

    const token = localStorage.getItem("authToken");
    if (!token) {
      setError("Authentication required. Please log in again.");
      return;
    }

    wsRef.current = new WebSocket(
      `${process.env.NEXT_PUBLIC_API_URL.replace(
        "http",
        "ws"
      )}/ws?token=${token}`
    );

    wsRef.current.onopen = async () => {
      wsRef.current.send(
        JSON.stringify({
          type: "config",
          config: config,
        })
      );

      await startAudioStream();

      if (mode !== "audio") {
        setVideoEnabled(true);
        setVideoSource(mode);
      }

      setIsStreaming(true);
      setIsConnected(true);
    };

    wsRef.current.onmessage = async (event) => {
      const response = JSON.parse(event.data);
      if (response.type === "audio") {
        const audioData = base64ToFloat32Array(response.data);
        playAudioData(audioData);
      }
    };

    wsRef.current.onerror = (error) => {
      setError("WebSocket error: " + error.message);
      setIsStreaming(false);
    };

    wsRef.current.onclose = (event) => {
      setIsStreaming(false);
      // Check if the close was due to authentication failure
      if (event.code === 1008) {
        setError("Authentication failed. Please log out and log in again.");
        // Clear the invalid token
        localStorage.removeItem("authToken");
        // Force page reload to show login screen
        window.location.reload();
      }
    };
  };

  // Initialize audio context and stream
  const startAudioStream = async () => {
    try {
      // Initialize audio context
      audioContextRef.current = new (window.AudioContext ||
        window.webkitAudioContext)({
        sampleRate: 16000, // Required by Gemini
      });

      // Get microphone stream
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true },
      });
      console.log("Audio stream started with echo cancellation");

      // Always share the audio stream with SpeechRecognition (for transcription)
      if (recognitionRef.current) {
        recognitionRef.current.stream = stream;
      }

      // Create audio input node
      const source = audioContextRef.current.createMediaStreamSource(stream);
      const processor = audioContextRef.current.createScriptProcessor(
        512,
        1,
        1
      );

      processor.onaudioprocess = (e) => {
        // If websocket is not open, try to reestablish it (once per second)
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
          if (Date.now() - lastWsConnectionAttemptRef.current > 1000) {
            console.log("Reestablishing websocket connection...");
            const token = localStorage.getItem("authToken");
            if (!token) {
              setError("Authentication required. Please log in again.");
              stopStream();
              return;
            }
            const ws = new WebSocket(
              `${process.env.NEXT_PUBLIC_API_URL.replace(
                "http",
                "ws"
              )}/ws?token=${encodeURIComponent(token)}`
            );
            ws.onopen = async () => {
              ws.send(
                JSON.stringify({
                  type: "config",
                  config: config,
                })
              );
            };
            ws.onmessage = async (event) => {
              const response = JSON.parse(event.data);
              if (response.type === "audio") {
                const audioData = base64ToFloat32Array(response.data);
                playAudioData(audioData);
              } else if (response.type === "interrupt") {
                console.log("Received interrupt response after reconnect.");
              }
            };
            ws.onerror = (error) => {
              setError("WebSocket error: " + error.message);
            };
            ws.onclose = (event) => {
              setIsStreaming(false);
            };
            wsRef.current = ws;
            lastWsConnectionAttemptRef.current = Date.now();
          }
          return; // Skip sending until connection is reestablished
        }

        if (wsRef.current?.readyState === WebSocket.OPEN) {
          const shouldSend =
            !config.isWakeWordEnabled || wakeWordDetectedRef.current;
          setIsAudioSending(shouldSend); // Update state immediately

          if (!shouldSend) {
            console.log(
              "Interrupt active or wake word not detected; skipping audio send."
            );
          }

          if (shouldSend) {
            const inputData = e.inputBuffer.getChannelData(0);

            // Add validation
            if (inputData.every((sample) => sample === 0)) {
              return;
            }

            const pcmData = float32ToPcm16(inputData);
            const base64Data = btoa(
              String.fromCharCode(...new Uint8Array(pcmData.buffer))
            );
            wsRef.current.send(
              JSON.stringify({
                type: "audio",
                data: base64Data,
              })
            );
          }
        }
      };

      source.connect(processor);
      processor.connect(audioContextRef.current.destination);

      audioInputRef.current = { source, processor, stream };
      setIsStreaming(true);
    } catch (err) {
      setError("Failed to access microphone: " + err.message);
    }
  };

  // Stop streaming
  const stopStream = () => {
    // Stop any active audio playback
    if (currentAudioSourceRef.current) {
      currentAudioSourceRef.current.stop();
      currentAudioSourceRef.current.disconnect();
      currentAudioSourceRef.current = null;
      isPlayingRef.current = false;
    }

    // Add transcript reset
    setWakeWordTranscript("");
    setWakeWordDetected(false);
    wakeWordDetectedRef.current = false;
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }

    if (audioInputRef.current) {
      const { source, processor, stream } = audioInputRef.current;
      source.disconnect();
      processor.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      audioInputRef.current = null;
    }

    if (chatMode === "video") {
      setVideoEnabled(false);
      setVideoSource(null);

      if (videoStreamRef.current) {
        videoStreamRef.current.getTracks().forEach((track) => track.stop());
        videoStreamRef.current = null;
      }
      if (videoIntervalRef.current) {
        clearInterval(videoIntervalRef.current);
        videoIntervalRef.current = null;
      }
    }

    // stop ongoing audio playback
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    if (wsRef.current) {
      // Clean up WebSocket event listeners
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.onclose = null;

      // Close and nullify
      wsRef.current.close();
      wsRef.current = null;
    }

    setIsStreaming(false);
    setIsConnected(false);
    setChatMode(null);
  };

  const playAudioData = async (audioData) => {
    // Create a queue for audio chunks
    if (!audioBufferRef.current) {
      audioBufferRef.current = [];
    }

    // Add new audio data to queue
    audioBufferRef.current.push(audioData);

    // If nothing is playing, start playback
    if (!isPlayingRef.current) {
      playNextChunk();
    }
  };

  const playNextChunk = async () => {
    if (!audioBufferRef.current || audioBufferRef.current.length === 0) {
      isPlayingRef.current = false;
      return;
    }

    // Get the next chunk from queue
    const chunk = audioBufferRef.current.shift();

    // Create buffer and source
    const buffer = audioContextRef.current.createBuffer(1, chunk.length, 24000);
    buffer.copyToChannel(chunk, 0);

    const source = audioContextRef.current.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContextRef.current.destination);

    // Start playing immediately
    source.start(0);
    isPlayingRef.current = true;
    currentAudioSourceRef.current = source;

    // When this chunk ends, play the next one
    source.onended = () => {
      if (audioBufferRef.current.length > 0) {
        playNextChunk();
      } else {
        isPlayingRef.current = false;
        currentAudioSourceRef.current = null;
      }
    };
  };

  useEffect(() => {
    let isMounted = true;

    if (videoEnabled && videoRef.current) {
      const startVideo = async () => {
        try {
          let stream;
          if (videoSource === "camera") {
            stream = await navigator.mediaDevices.getUserMedia({
              video: { width: { ideal: 320 }, height: { ideal: 240 } },
            });
          } else if (videoSource === "screen") {
            stream = await navigator.mediaDevices.getDisplayMedia({
              video: { width: { ideal: 1920 }, height: { ideal: 1080 } },
            });
          }

          videoRef.current.srcObject = stream;
          videoStreamRef.current = stream;

          // Start frame capture after video is playing
          videoIntervalRef.current = setInterval(() => {
            captureAndSendFrame();
          }, 1000);
        } catch (err) {
          console.error("Video initialization error:", err);
          setError("Failed to access camera/screen: " + err.message);

          if (videoSource === "screen") {
            // Reset chat mode and clean up any existing connections
            setChatMode(null);
            stopStream();
          }

          setVideoEnabled(false);
          setVideoSource(null);
        }
      };

      startVideo();

      // Cleanup function
      return () => {
        if (!isMounted) return;

        if (videoStreamRef.current) {
          videoStreamRef.current.getTracks().forEach((track) => track.stop());
          videoStreamRef.current = null;
        }
        if (videoIntervalRef.current) {
          clearInterval(videoIntervalRef.current);
          videoIntervalRef.current = null;
        }
      };
    }
  }, [videoEnabled, videoSource]);

  // Frame capture function
  const captureAndSendFrame = () => {
    if (!canvasRef.current || !videoRef.current || !wsRef.current) return;

    const context = canvasRef.current.getContext("2d");
    if (!context) return;

    canvasRef.current.width = videoRef.current.videoWidth;
    canvasRef.current.height = videoRef.current.videoHeight;

    context.drawImage(videoRef.current, 0, 0);
    const base64Image = canvasRef.current.toDataURL("image/jpeg").split(",")[1];

    wsRef.current.send(
      JSON.stringify({
        type: "image",
        data: base64Image,
      })
    );
  };

  // Toggle video function
  const toggleVideo = () => {
    setVideoEnabled(!videoEnabled);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (videoStreamRef.current) {
        videoStreamRef.current.getTracks().forEach((track) => track.stop());
      }
      stopStream();

      // Clean up audio context
      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }
    };
  }, []);

  // Wake word detection
  useEffect(() => {
    // Always initialize SpeechRecognition for continuous transcription.
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onstart = () => {
        console.log("Speech recognition started");
      };

      recognition.onend = (event) => {
        console.log("Speech recognition ended", event);
        // Restart recognition if streaming is active (helps capture interrupts even when Gemini is talking)
        if (isStreaming && recognitionRef.current === recognition) {
          try {
            // Add a small delay to prevent rapid restart loops
            setTimeout(() => {
              if (isStreaming && recognitionRef.current === recognition) {
                recognition.start();
                console.log("Speech recognition restarted");
              }
            }, 300);
          } catch (err) {
            console.log("Failed to restart speech recognition:", err);
          }
        }
      };

      recognition.onerror = (event) => {
        console.log("Speech recognition error:", event.error);
        if (event.error === "not-allowed" || event.error === "audio-capture") {
          setError("Microphone already in use - disable wake word to continue");
        }
      };

      recognition.onresult = (event) => {
        const latestResult = event.results[event.results.length - 1];
        const transcript = latestResult[0].transcript;
        console.log("SpeechRecognition result:", transcript);
        setWakeWordTranscript(transcript);

        // Always process final transcript
        if (latestResult.isFinal) {
          const lcTranscript = transcript.toLowerCase();

          // If cancellation is allowed and the cancel phrase is detected, send an interrupt
          if (
            config.cancelPhrase &&
            lcTranscript.includes(config.cancelPhrase.toLowerCase())
          ) {
            if (Date.now() - lastInterruptTimeRef.current < 1000) {
              console.log("Interrupt debounced");
              setWakeWordTranscript("");
              return;
            }
            lastInterruptTimeRef.current = Date.now();
            console.log(
              "Final transcript triggering interrupt (cancel phrase detected):",
              transcript
            );
            const sendInterrupt = () => {
              console.log("Active generation detected; sending interrupt.");
              audioBufferRef.current = [];
              wakeWordDetectedRef.current = false;
              setWakeWordDetected(false);

              if (currentAudioSourceRef.current) {
                console.log("Stopping current audio source due to interrupt.");
                currentAudioSourceRef.current.stop();
                currentAudioSourceRef.current = null;
              }
              if (
                wsRef.current &&
                wsRef.current.readyState === WebSocket.OPEN
              ) {
                wsRef.current.send(JSON.stringify({ type: "interrupt" }));
                console.log("Interrupt message sent to backend via WebSocket.");
                // Do not close the websocket connection; this lets new audio be sent after interrupt.
              } else {
                console.log("WebSocket not open or unavailable for interrupt.");
              }
            };
            if (
              audioBufferRef.current.length > 0 ||
              currentAudioSourceRef.current !== null
            ) {
              sendInterrupt();
            } else {
              console.log(
                "No active generation detected; scheduling delayed check for interrupt (300ms)..."
              );
              setTimeout(() => {
                if (
                  audioBufferRef.current.length > 0 ||
                  currentAudioSourceRef.current !== null
                ) {
                  sendInterrupt();
                } else {
                  console.log(
                    "Delayed check: Still no active generation; not sending interrupt."
                  );
                }
              }, 300);
            }
          }

          // Independently check for wake word if enabled
          if (
            config.isWakeWordEnabled &&
            lcTranscript.includes(config.wakeWord.toLowerCase())
          ) {
            console.log(
              "Wake word detected; enabling audio transmission:",
              transcript
            );
            setWakeWordDetected(true);
            wakeWordDetectedRef.current = true;

            // Reset any interrupt state and ensure audio transmission
            audioBufferRef.current = [];
            if (currentAudioSourceRef.current) {
              currentAudioSourceRef.current.stop();
              currentAudioSourceRef.current = null;
            }

            // Force reconnection if needed
            if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
              console.log("Reconnecting WebSocket after wake word detection");
              const token = localStorage.getItem("authToken");
              if (!token) {
                setError("Authentication required. Please log in again.");
                stopStream();
                return;
              }
              const ws = new WebSocket(
                `ws://54.158.95.38:8000/ws?token=${encodeURIComponent(token)}`
              );
              ws.onopen = async () => {
                ws.send(JSON.stringify({ type: "config", config: config }));
                setIsStreaming(true);
                setIsConnected(true);
              };
              wsRef.current = ws;
            }
          }

          if (
            (config.allowInterruptions || config.isWakeWordEnabled) &&
            !(
              (config.allowInterruptions &&
                lcTranscript.includes(config.cancelPhrase.toLowerCase())) ||
              (config.isWakeWordEnabled &&
                lcTranscript.includes(config.wakeWord.toLowerCase()))
            )
          ) {
            console.log(
              "Final transcript does not contain wake word or cancel phrase:",
              transcript
            );
            // Retain the transcript for debugging
            setWakeWordTranscript(transcript);
          }
        }
      };

      try {
        recognition.start();
        recognitionRef.current = recognition;
      } catch (err) {
        setError("Microphone access error: " + err.message);
      }
    } else {
      setError("Speech recognition not supported in this browser");
    }

    return () => {
      wakeWordDetectedRef.current = false;
      if (recognitionRef.current) {
        recognitionRef.current.stop();
        recognitionRef.current = null;
      }
    };
  }, [config.wakeWord, config.cancelPhrase, isStreaming]);

  return (
    <div className="container mx-auto px-4 sm:px-6 md:px-8 h-screen flex flex-col">
      <div className="space-y-6 relative z-10 flex-grow">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-indigo-900/40 via-purple-900/20 to-transparent rounded-3xl blur-xl"></div>
        <div className="pt-2">
          <HeaderButtons 
            isConnected={isConnected} 
            config={config}
            setConfig={setConfig}
            onLogout={onLogout} 
          />
        </div>
        <div className="flex flex-col items-center justify-center w-full min-h-[20vh]">
          <div className="flex flex-col items-center justify-center gap-2 w-full">
            <div className="text-4xl glow-text">✨</div>
            <h1 className="text-4xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-purple-400 via-pink-500 to-indigo-400 glow-text">
              Awaken Ambience
            </h1>
          </div>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="flex justify-center w-full my-6">
          <ControlButtons
            isStreaming={isStreaming}
            startStream={startStream}
            stopStream={stopStream}
          />
        </div>

        {isStreaming && (
          <AudioStatus
            isAudioSending={isAudioSending}
            isWakeWordEnabled={config.isWakeWordEnabled}
            wakeWordDetected={wakeWordDetected}
          />
        )}

        {chatMode === "video" && (
          <VideoDisplay
            videoRef={videoRef}
            canvasRef={canvasRef}
            videoSource={videoSource}
          />
        )}

        <WakeWordIndicator wakeWordDetected={wakeWordDetected} />

        {config.isWakeWordEnabled && (
          <WakeWordDebug
            isStreaming={isStreaming}
            wakeWordTranscript={wakeWordTranscript}
            wakeWord={config.wakeWord}
          />
        )}
      </div>
    </div>
  );
}
