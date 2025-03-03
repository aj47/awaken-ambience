from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from websockets import connect
from typing import Dict
from db import MemoryDB

load_dotenv()

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GeminiConnection:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.model = "gemini-2.0-flash-exp"
        self.uri = (
            "wss://generativelanguage.googleapis.com/ws/"
            "google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"
            f"?key={self.api_key}"
        )
        self.ws = None
        self.config = None
        self.interrupted = False
        self.memory_db = MemoryDB()

    async def connect(self):
        """Initialize connection to Gemini"""
        self.ws = await connect(self.uri, additional_headers={"Content-Type": "application/json"})
        
        if not self.config:
            raise ValueError("Configuration must be set before connecting")

        # Get all memories and format them into the system prompt
        memories = self.memory_db.get_all_memories(self.config.get("client_id", "default"))
        memory_context = "\n".join([f"- {memory[0]}" for memory in memories])
        
        # Send initial setup message with configuration
        setup_message = {
            "setup": {
                "model": f"models/{self.model}",
                "generation_config": {
                    "response_modalities": ["AUDIO"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {
                                "voice_name": self.config["voice"]
                            }
                        }
                    }
                },
                "tools": [
                    { "googleSearch": {} },
                    {
                        "function_declarations": [
                            {
                                "name": "store_memory",
                                "description": "Stores a memory in the database using MemoryDB.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "client_id": { "type": "string" },
                                        "content": { "type": "string" },
                                        "context": { "type": "string" },
                                        "tags": { "type": "array", "items": { "type": "string" } },
                                        "type": { "type": "string" }
                                    }
                                }
                            },
                            {
                                "name": "get_recent_memories",
                                "description": "Retrieves recent memories from the database.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "client_id": { "type": "string" },
                                        "limit": { "type": "integer" }
                                    }
                                }
                            },
                            {
                                "name": "search_memories",
                                "description": "Searches memories based on query.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "client_id": { "type": "string" },
                                        "query": { "type": "string" },
                                        "limit": { "type": "integer" }
                                    }
                                }
                            },
                            {
                                "name": "delete_memory",
                                "description": "Deletes a specific memory by its ID.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "memory_id": { "type": "integer" }
                                    }
                                }
                            },
                            {
                                "name": "update_memory",
                                "description": "Updates the content of a specific memory.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "memory_id": { "type": "integer" },
                                        "new_content": { "type": "string" }
                                    }
                                }
                            }
                        ]
                    }
                ],
                "system_instruction": {
                    "parts": [
                        {
                            "text": self.config["systemPrompt"] + 
                            "\n\nHere are recent memories:\n" + memory_context +
                            "\n\nYou can also use the memory functions store_memory, get_recent_memories, and search_memories."
                        }
                    ]
                }
            }
        }
        await self.ws.send(json.dumps(setup_message))
        
        # Wait for setup completion
        setup_response = await self.ws.recv()
        return setup_response

    def set_config(self, config):
        """Set configuration for the connection"""
        self.config = config

    async def send_audio(self, audio_data: str):
        """Send audio data to Gemini"""
        realtime_input_msg = {
            "realtime_input": {
                "media_chunks": [
                    {
                        "data": audio_data,
                        "mime_type": "audio/pcm"
                    }
                ]
        }
        }
        await self.ws.send(json.dumps(realtime_input_msg))

    async def receive(self):
        """Receive message from Gemini"""
        return await self.ws.recv()

    async def close(self):
        """Close the connection"""
        if self.ws:
            print("Closing Gemini websocket connection.")
            await self.ws.close()
            self.ws = None

    async def handle_tool_call(self, tool_call):
        responses = []
        for f in tool_call.get("functionCalls", []):
            print(f"  <- Function call: {f}")
            func_name = f.get("name")
            args = f.get("args", {})
            if func_name == "store_memory":
                result = self.memory_db.store_memory(
                    args.get("client_id", ""),
                    args.get("content", ""),
                    args.get("context", ""),
                    args.get("tags", []),
                    args.get("type", "")
                )
                response_text = f"Stored memory: {args.get('content', '')[:50]}..."
            elif func_name == "get_recent_memories":
                result = self.memory_db.get_recent_memories(
                    args.get("client_id", ""),
                    args.get("limit", 5)
                )
                response_text = f"Here are your recent memories:\n"
                for i, memory in enumerate(result, 1):
                    response_text += f"{i}. {memory[0][:100]}...\n"
            elif func_name == "search_memories":
                result = self.memory_db.search_memories(
                    args.get("client_id", ""),
                    args.get("query", ""),
                    args.get("limit", 5)
                )
                response_text = f"Found {len(result)} memories matching '{args.get('query', '')}':\n"
                for i, memory in enumerate(result, 1):
                    response_text += f"{i}. {memory[0][:100]}...\n"
            elif func_name == "delete_memory":
                self.memory_db.delete_memory(args.get("memory_id"))
                response_text = f"Successfully deleted memory ID {args.get('memory_id')}"
            elif func_name == "update_memory":
                self.memory_db.update_memory(
                    args.get("memory_id"),
                    args.get("new_content")
                )
                response_text = f"Successfully updated memory ID {args.get('memory_id')}"
            else:
                result = {"error": f"Unknown function {func_name}"}
                response_text = f"Sorry, I don't know how to handle that function."

            responses.append({
                "id": f.get("id"),
                "name": func_name,
                "response": {
                    "name": func_name,
                    "content": result
                }
            })

            # Send a verbal response about the tool call result
            await self.ws.send(json.dumps({
                "clientContent": {
                    "turns": [{
                        "parts": [{"text": response_text}],
                        "role": "user"
                    }],
                    "turnComplete": True
                }
            }))

        tool_response = {
            "toolResponse": {
                "functionResponses": responses
            }
        }
        await self.ws.send(json.dumps(tool_response))

    async def send_image(self, image_data: str):
        """Send image data to Gemini"""
        image_message = {
            "realtime_input": {
                "media_chunks": [
                    {
                        "data": image_data,
                        "mime_type": "image/jpeg"
                    }
                ]
            }
        }
        await self.ws.send(json.dumps(image_message))


# Store active connections
connections: Dict[str, GeminiConnection] = {}
memory_db = MemoryDB()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    
    try:
        
        # Create new Gemini connection for this client
        gemini = GeminiConnection()
        connections[client_id] = gemini
        
        # Wait for initial configuration
        config_data = await websocket.receive_json()
        if config_data.get("type") != "config":
            raise ValueError("First message must be configuration")
        
        # Set the configuration
        gemini.set_config(config_data.get("config", {}))
        
        # Initialize Gemini connection
        await gemini.connect()
        
        # Handle bidirectional communication
        async def receive_from_client():
            try:
                while True:
                    try:
                        # Check if connection is closed
                        if websocket.client_state.value == 3:  # WebSocket.CLOSED
                            return

                        message_text = await websocket.receive_text()
                
                        message_content = json.loads(message_text)
                        msg_type = message_content["type"]
                        if msg_type == "audio":
                            if gemini.interrupted:
                                gemini.interrupted = False  # Resume with a new generation if audio arrives after an interrupt
                            if not gemini.ws:
                                print(f"[Client {client_id}] Gemini connection is closed. Reconnecting...")
                                await gemini.connect()
                            
                            # Skip storing raw audio messages
                            pass
                            
                            await gemini.send_audio(message_content["data"])    
                        elif msg_type == "image":
                            await gemini.send_image(message_content["data"])
                        elif msg_type == "interrupt":
                            print(f"[Client {client_id}] Received interrupt command from client, canceling current Gemini generation.")
                            gemini.interrupted = True  # Mark the current generation as canceled
                            await websocket.send_json({
                                "type": "interrupt",
                                "message": "Generation canceled."
                            })
                            continue
                        else:
                            print(f"Unknown message type: {msg_type}")
                    except json.JSONDecodeError as e:
                        print(f"JSON decode error: {e}")
                        continue
                    except KeyError as e:
                        print(f"Key error in message: {e}")
                        continue
                    except Exception as e:
                        print(f"Error processing client message: {str(e)}")
                        if "disconnect message" in str(e):
                            return
                        continue
                            
            except Exception as e:
                print(f"Fatal error in receive_from_client: {str(e)}")
                return

        async def receive_from_gemini():
            try:
                while True:
                    if websocket.client_state.value == 3:
                        print("WebSocket closed, stopping Gemini receiver")
                        return

                    try:
                        msg = await gemini.receive()
                        response = json.loads(msg)
                        print("rcv:", response)
                        if "toolCall" in response:
                            await gemini.handle_tool_call(response["toolCall"])
                            continue
                        # Only store meaningful text responses
                        if "serverContent" in response:
                            content = response["serverContent"]
                            if "modelTurn" in content and "text" in str(content["modelTurn"]):
                                print(f"[Memory] Storing response for client {client_id}")
                                memory_db.store_memory(
                                    client_id,
                                    json.dumps(content["modelTurn"]),
                                    "response"
                                )
                    except Exception as ex:
                        print(f"Gemini receive error: {ex}")
                        break
            
                    # Add error logging
            
                    try:
                        # Handle different response structures
                        if "serverContent" in response:
                            content = response["serverContent"]
                            if "modelTurn" in content:
                                parts = content["modelTurn"]["parts"]
                            elif "candidates" in content:
                                parts = content["candidates"][0]["content"]["parts"]
                            else:
                                parts = []
                        else:
                            parts = []
                
                        for p in parts:
                            if websocket.client_state.value == 3:
                                return
       
                            # If an interrupt was issued, skip sending any remaining audio chunks.
                            if gemini.interrupted:
                                continue
       
                            if "inlineData" in p:
                                # Truncate audio data in debug output
                                data = p['inlineData']['data']
                                print(f"Sending audio response ({len(data)} bytes): {data[:1]}...")
                                await websocket.send_json({
                                    "type": "audio",
                                    "data": p["inlineData"]["data"]
                                })
                    except KeyError as e:
                        print(f"KeyError processing Gemini response: {e}")
                        continue

                    # Handle turn completion
                    try:
                        if response.get("serverContent", {}).get("turnComplete") and not gemini.interrupted:
                            await websocket.send_json({
                                "type": "turn_complete",
                                "data": True
                            })
                    except Exception as e:
                        print(f"Error processing turn completion: {e}")
                        continue
            except Exception as e:
                print(f"Error receiving from Gemini: {e}")

        # Run both receiving tasks concurrently
        async with asyncio.TaskGroup() as tg:
            tg.create_task(receive_from_client())
            tg.create_task(receive_from_gemini())

    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Cleanup
        if client_id in connections:
            await connections[client_id].close()
            del connections[client_id]

@app.get("/memories")
async def get_memories():
    """Get all memories"""
    try:
        memories = memory_db.get_all_memories()
        return [
            {
                "id": memory[0],  # Assuming first column is id
                "content": memory[1],
                "timestamp": memory[2],
                "type": memory[3]
            }
            for memory in memories
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memories/{memory_id}")
async def get_memory(memory_id: int):
    """Get a specific memory by ID"""
    try:
        memory = memory_db.get_memory(memory_id)
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {
            "id": memory[0],
            "content": memory[1],
            "timestamp": memory[2],
            "type": memory[3]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/memories/{memory_id}")
async def delete_memory(memory_id: int):
    """Delete a specific memory"""
    try:
        memory_db.delete_memory(memory_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
