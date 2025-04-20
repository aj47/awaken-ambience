"use client";

import React, { useState, useRef, useEffect } from "react";
import { Mic, StopCircle, Video, Monitor } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { base64ToFloat32Array, float32ToPcm16 } from "@/lib/utils";

// Import our components
import AudioStatus from "./audio-status";
import VideoDisplay from "./video-display";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ControlButtons from "./control-buttons";
import HeaderButtons from "./header-buttons";
import { Label } from "@/components/ui/label"; // Keep Label import if used elsewhere, otherwise remove if only for the moved selector

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
    getVideoDevices(); // Fetch video devices on mount
    getAudioDevices(); // Fetch audio devices on mount
  }, []);

  // Function to get available audio devices
  const getAudioDevices = async () => {
    try {
      if (!navigator.mediaDevices?.enumerateDevices) {
        console.warn("enumerateDevices() not supported.");
        return;
      }
      const devices = await navigator.mediaDevices.enumerateDevices();
      const audioInputs = devices.filter(device => device.kind === 'audioinput');
      setAudioDevices(audioInputs);
      if (audioInputs.length > 0 && !selectedAudioDeviceId) {
        setSelectedAudioDeviceId(audioInputs[0].deviceId); // Select the first device by default
      }
    } catch (err) {
      console.error("Error enumerating audio devices:", err);
      setError("Could not list audio devices.");
    }
  };


  // Function to get available video devices
  const getVideoDevices = async () => {
    try {
      if (!navigator.mediaDevices?.enumerateDevices) {
        console.warn("enumerateDevices() not supported.");
        return;
      }
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoInputs = devices.filter(device => device.kind === 'videoinput');
      setVideoDevices(videoInputs);
      if (videoInputs.length > 0 && !selectedVideoDeviceId) {
        setSelectedVideoDeviceId(videoInputs[0].deviceId); // Select the first device by default
      }
    } catch (err) {
      console.error("Error enumerating video devices:", err);
      setError("Could not list video devices.");
    }
  };

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
  const isInterruptedRef = useRef<boolean>(false);
  const [videoEnabled, setVideoEnabled] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoStreamRef = useRef<MediaStream | null>(null);
  const videoIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const [chatMode, setChatMode] = useState<"audio" | "video" | null>(null);
  const [videoSource, setVideoSource] = useState<"camera" | "screen" | null>(null);
  const [videoDevices, setVideoDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedVideoDeviceId, setSelectedVideoDeviceId] = useState<string | null>(null);
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedAudioDeviceId, setSelectedAudioDeviceId] = useState<string | null>(null);

  const voices = ["Puck", "Charon", "Kore", "Fenrir", "Aoede"];
  const audioBufferRef = useRef<Float32Array[]>([]);
  const isPlayingRef = useRef(false);
  const currentAudioSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const sfxAudioRef = useRef<HTMLAudioElement | null>(null);

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
      } else if (response.type === "interrupt") {
        console.log("Received interrupt confirmation from server:", response);
      } else if (response.type === "interrupt_confirmed") {
        console.log("Received interrupt_confirmed from Gemini API:", response);
        stopAudio(); // Stop audio playback when interrupt is confirmed
      } else if (response.type === "stop_audio") {
        console.log("Received stop_audio command from server");
        stopAudio(); // Stop audio playback
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

      // Get microphone stream using selected device
      const audioConstraints: MediaTrackConstraints = {
        echoCancellation: true,
        deviceId: selectedAudioDeviceId ? { exact: selectedAudioDeviceId } : undefined
      };
      console.log("Requesting audio stream with constraints:", audioConstraints);
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: audioConstraints,
      });
      console.log("Audio stream started");

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
                console.log("Received interrupt confirmation from server:", response);
              } else if (response.type === "interrupt_confirmed") {
                console.log("Received interrupt_confirmed from Gemini API:", response);
                stopAudio(); // Stop audio playback when interrupt is confirmed
              } else if (response.type === "stop_audio") {
                console.log("Received stop_audio command from server");
                stopAudio(); // Stop audio playback
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
            (!config.isWakeWordEnabled || wakeWordDetectedRef.current) && !isInterruptedRef.current;
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

  // Function to play sound effects
  const playSoundEffect = (reverse = false) => {
    try {
      // For normal playback, use the HTML Audio element
      if (!reverse) {
        // Create a new audio element if it doesn't exist
        if (!sfxAudioRef.current) {
          sfxAudioRef.current = new Audio('/sfx.mp3');
        }

        // Reset the audio to the beginning
        sfxAudioRef.current.currentTime = 0;

        // Play the sound normally
        sfxAudioRef.current.play().catch(err => {
          console.error('Error playing sound effect:', err);
        });
      }
      // For reverse playback, use the Web Audio API
      else if (audioContextRef.current) {
        // Fetch the sound file
        fetch('/sfx.mp3')
          .then(response => response.arrayBuffer())
          .then(arrayBuffer => audioContextRef.current.decodeAudioData(arrayBuffer))
          .then(audioBuffer => {
            // Create a reversed copy of the audio data
            const reversedBuffer = audioContextRef.current.createBuffer(
              audioBuffer.numberOfChannels,
              audioBuffer.length,
              audioBuffer.sampleRate
            );

            // Copy and reverse each channel
            for (let channel = 0; channel < audioBuffer.numberOfChannels; channel++) {
              const channelData = audioBuffer.getChannelData(channel);
              const reversedData = reversedBuffer.getChannelData(channel);
              for (let i = 0; i < channelData.length; i++) {
                reversedData[i] = channelData[channelData.length - 1 - i];
              }
            }

            // Create a new buffer source for the reversed audio
            const source = audioContextRef.current.createBufferSource();
            source.buffer = reversedBuffer;
            source.connect(audioContextRef.current.destination);
            source.start();
          })
          .catch(err => console.error('Error playing reversed sound effect:', err));
      }
    } catch (err) {
      console.error('Error with sound effect playback:', err);
    }
  };

  // Function to stop audio playback
  const stopAudio = () => {
    isInterruptedRef.current = true;

    if (currentAudioSourceRef.current) {
      currentAudioSourceRef.current.stop();
      currentAudioSourceRef.current = null;
    }
    audioBufferRef.current = [];
    isPlayingRef.current = false;

    // Reset the interrupted state after a short delay
    // Only if wake word is not enabled or if wake word is detected
    // This ensures we stay in sleep mode when needed
    if (!config.isWakeWordEnabled || wakeWordDetectedRef.current) {
      setTimeout(() => {
        isInterruptedRef.current = false;
      }, 500);
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

    // Don't buffer audio if we're in an interrupted state
    if (isInterruptedRef.current) {
      console.log("Skipping audio buffering due to active interruption");
      return;
    }

    // Add new audio data to queue
    audioBufferRef.current.push(audioData);

    // If nothing is playing, start playback
    if (!isPlayingRef.current) {
      playNextChunk();
    }
  };

  const playNextChunk = async () => {
    if (!audioBufferRef.current || audioBufferRef.current.length === 0 || isInterruptedRef.current) {
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
      if (audioBufferRef.current.length > 0 && !isInterruptedRef.current) {
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
          let stream: MediaStream;
          if (videoSource === "camera") {
            const constraints: MediaStreamConstraints = {
              video: {
                width: { ideal: 320 },
                height: { ideal: 240 },
                deviceId: selectedVideoDeviceId ? { exact: selectedVideoDeviceId } : undefined
              }
            };
            console.log("Requesting camera stream with constraints:", constraints);
            stream = await navigator.mediaDevices.getUserMedia(constraints);
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
            // Play the sound effect in reverse for sleep word
            playSoundEffect(true);

            const sendInterrupt = () => {
              console.log("Active generation detected; sending interrupt.");

              // If wake word is enabled, we need to fully deactivate it
              if (config.isWakeWordEnabled) {
                console.log("Sleep word detected; disabling audio transmission");
                wakeWordDetectedRef.current = false;
                setWakeWordDetected(false);
                setWakeWordTranscript("");

                // Show a visual indicator that sleep mode is active
                setError("Sleep mode activated. Say the wake word to resume.");
                // Clear the error message after 3 seconds
                setTimeout(() => {
                  setError(null);
                }, 3000);
              }

              audioBufferRef.current = [];

              // Set the interrupted flag to prevent buffering new audio
              isInterruptedRef.current = true;

              if (currentAudioSourceRef.current) {
                console.log("Stopping current audio source due to interrupt.");
                currentAudioSourceRef.current.stop();
                currentAudioSourceRef.current = null;
              }

              // Clear any buffered audio
              audioBufferRef.current = [];
              if (
                wsRef.current &&
                wsRef.current.readyState === WebSocket.OPEN
              ) {
                wsRef.current.send(JSON.stringify({ type: "interrupt" }));
                console.log("Interrupt message sent to backend via WebSocket.");

                // Only show interrupting message if wake word is not enabled
                if (!config.isWakeWordEnabled) {
                  // Show a visual indicator that interruption is in progress
                  setError("Interrupting Gemini...");
                  // Clear the error message after 2 seconds
                  setTimeout(() => {
                    setError(null);
                  }, 2000);
                }
                // Do not close the websocket connection; this lets new audio be sent after interrupt.
              } else {
                console.log("WebSocket not open or unavailable for interrupt.");
              }
            };
            // Always send the interrupt signal to the backend when cancel phrase is detected
            sendInterrupt();
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

            // Play the wake word sound effect
            playSoundEffect(false);

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
            isConnected={isConnected}
            config={config}
            setConfig={setConfig}
            onLogout={onLogout}
            audioDevices={audioDevices}
            selectedAudioDeviceId={selectedAudioDeviceId}
            setSelectedAudioDeviceId={setSelectedAudioDeviceId}
            videoDevices={videoDevices}
            selectedVideoDeviceId={selectedVideoDeviceId}
            setSelectedVideoDeviceId={setSelectedVideoDeviceId}
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

        {/* Camera selector removed from here */}

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
      </div>
    </div>
  );
}
