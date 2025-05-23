import logging
from fastapi import FastAPI, WebSocket, HTTPException, Depends, status, Request, WebSocketDisconnect
from starlette.websockets import WebSocketState # Added import
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from security import get_current_user_websocket, create_access_token, authenticate_user, get_password_hash, ACCESS_TOKEN_EXPIRE_MINUTES
from jose import JWTError, jwt
from security import SECRET_KEY, ALGORITHM
from typing import Annotated
import asyncio
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from websockets import connect, exceptions as ws_exceptions # Added exceptions import
from websockets.connection import State
from typing import Dict
from db import MemoryDB

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Add user model
class User:
    def __init__(self, username: str, hashed_password: str):
        self.username = username
        self.hashed_password = hashed_password

# Temporary in-memory user database (replace with real DB in production)
fake_users_db = {
    "admin": User(
        username="admin",
        hashed_password=get_password_hash("admin")
    )
}

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
        self.username = None # Added to store username
        self.interrupt_sent = False # Flag to track if interrupt was sent to Gemini API

    async def connect(self):
        """Initialize connection to Gemini"""
        logger.info(f"[GeminiConnection-{self.username}] Attempting to connect to Gemini at {self.uri}")
        try:
            self.ws = await connect(self.uri, additional_headers={"Content-Type": "application/json"})
            logger.info(f"[GeminiConnection-{self.username}] WebSocket connection established.")
        except Exception as e:
            logger.error(f"[GeminiConnection-{self.username}] Failed to connect to Gemini: {e}")
            raise

        if not self.config:
            logger.error(f"[GeminiConnection-{self.username}] Configuration must be set before connecting.")
            raise ValueError("Configuration must be set before connecting")

        logger.info(f"[GeminiConnection-{self.username}] Fetching memories for system prompt.")
        # Get all memories and format them into the system prompt
        try:
            memories = self.memory_db.get_all_memories(self.username)
            memory_context = "\n".join([f"- {memory[1]}" for memory in memories]) # Assuming memory content is at index 1
        except Exception as e:
            logger.error(f"[GeminiConnection-{self.username}] Error fetching memories: {e}")
            memory_context = "Could not retrieve memories."

        # Send initial setup message with configuration
        logger.info(f"[GeminiConnection-{self.username}] Sending setup message.")
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
                            "\n\nUse the memory function often."
                        }
                    ]
                }
            }
        }
        try:
            await self.ws.send(json.dumps(setup_message))

            # Wait for setup completion
            logger.info(f"[GeminiConnection-{self.username}] Waiting for setup response.")
            setup_response = await self.ws.recv()
            logger.info(f"[GeminiConnection-{self.username}] Received setup response: {setup_response[:100]}...") # Log truncated response
            return setup_response
        except Exception as e:
            logger.error(f"[GeminiConnection-{self.username}] Error during setup communication: {e}")
            await self.close() # Ensure connection is closed on error
            raise

    def set_config(self, config):
        """Set configuration for the connection"""
        # Validate and normalize config
        if not isinstance(config, dict):
            raise ValueError("Config must be a dictionary")

        # Ensure systemPrompt is properly named
        if "systemPrompt" in config:
            config["systemPrompt"] = config["systemPrompt"]

        self.config = config
        logger.info(f"[GeminiConnection-{self.username}] Config set: {self.config}")

    async def send_audio(self, audio_data: str):
        """Send audio data to Gemini"""
        # Check Gemini connection state correctly
        if not self.ws or self.ws.state == State.CLOSED:
            logger.warning(f"[GeminiConnection-{self.username}] Attempted to send audio while WebSocket is closed or None.")
            return

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
        try:
            await self.ws.send(json.dumps(realtime_input_msg))
        except Exception as e:
            logger.error(f"[GeminiConnection-{self.username}] Error sending audio data: {e}")
            await self.close()

    async def send_interrupt(self):
        """Send an interrupt signal to Gemini to stop the current generation"""
        # Check Gemini connection state correctly
        if not self.ws or self.ws.state == State.CLOSED:
            logger.warning(f"[GeminiConnection-{self.username}] Attempted to send interrupt while WebSocket is closed or None.")
            return False

        # Set the interrupted flag immediately to stop sending audio
        self.interrupted = True
        self.interrupt_sent = True

        # Send the interrupt message to Gemini
        interrupt_msg = {
            "realtime_input": {
                "interrupt": {}
            }
        }

        try:
            logger.info(f"[GeminiConnection-{self.username}] Sending interrupt signal to Gemini API.")
            await self.ws.send(json.dumps(interrupt_msg))
            logger.info(f"[GeminiConnection-{self.username}] Interrupt signal sent successfully.")
            return True
        except Exception as e:
            logger.error(f"[GeminiConnection-{self.username}] Error sending interrupt signal: {e}")
            await self.close()
            return False

    async def receive(self):
        """Receive message from Gemini"""
        # Check Gemini connection state correctly
        if not self.ws or self.ws.state == State.CLOSED:
            logger.warning(f"[GeminiConnection-{self.username}] Attempted to receive while WebSocket is closed or None.")
            raise WebSocketDisconnect(code=1000, reason="Gemini WS closed") # Signal closure

        try:
            message = await self.ws.recv()
            return message
        except Exception as e:
            logger.error(f"[GeminiConnection-{self.username}] Error receiving message from Gemini: {e}")
            await self.close() # Ensure connection is closed on error
            raise # Re-raise the exception

    async def close(self):
        """Close the connection"""
        # Use self.ws.state to check connection status correctly
        if self.ws and self.ws.state != State.CLOSED:
            logger.info(f"[GeminiConnection-{self.username}] Closing Gemini websocket connection.")
            try:
                # Add a timeout to close to prevent hanging
                await asyncio.wait_for(self.ws.close(), timeout=5.0)
                logger.info(f"[GeminiConnection-{self.username}] Gemini websocket connection closed.")
            except Exception as e:
                logger.error(f"[GeminiConnection-{self.username}] Error closing Gemini websocket: {e}")
            finally:
                self.ws = None
        elif self.ws and self.ws.state == State.CLOSED: # Check state correctly here too
             logger.info(f"[GeminiConnection-{self.username}] Gemini websocket connection already closed.")
             self.ws = None
        else:
            logger.info(f"[GeminiConnection-{self.username}] No active Gemini websocket connection to close.")


    async def handle_tool_call(self, tool_call):
        responses = []
        logger.info(f"[GeminiConnection-{self.username}] Handling tool call: {tool_call}")
        for f in tool_call.get("functionCalls", []):
            logger.info(f"[GeminiConnection-{self.username}]   <- Function call: {f}")
            func_name = f.get("name")
            args = f.get("args", {})
            response_text = "Tool call processed." # Default response text
            result = None
            try:
                if func_name == "store_memory":
                    result = self.memory_db.store_memory(
                        content=args.get("content", ""),
                        username=self.username,
                        type=args.get("type", "conversation"),
                    context=args.get("context", ""),
                        tags=args.get("tags", [])
                    )
                    response_text = f"Stored memory: {args.get('content', '')[:50]}..."
                    logger.info(f"[GeminiConnection-{self.username}] Stored memory via tool call.")
                elif func_name == "get_recent_memories":
                    result = self.memory_db.get_recent_memories(
                        self.username,
                        args.get("limit", 5)
                    )
                    response_text = f"Here are your recent memories:\n"
                    for i, memory in enumerate(result or [], 1):
                        response_text += f"{i}. {memory[1][:100]}...\n" # Assuming content at index 1
                    logger.info(f"[GeminiConnection-{self.username}] Retrieved recent memories via tool call.")
                elif func_name == "search_memories":
                    result = self.memory_db.search_memories(
                        self.username,
                        args.get("query", ""),
                        args.get("limit", 5)
                    )
                    response_text = f"Found {len(result or [])} memories matching '{args.get('query', '')}':\n"
                    for i, memory in enumerate(result or [], 1):
                        response_text += f"{i}. {memory[1][:100]}...\n" # Assuming content at index 1
                    logger.info(f"[GeminiConnection-{self.username}] Searched memories via tool call.")
                elif func_name == "delete_memory":
                    memory_id = args.get("memory_id")
                    self.memory_db.delete_memory(memory_id, self.username)
                    response_text = f"Successfully deleted memory ID {memory_id}"
                    logger.info(f"[GeminiConnection-{self.username}] Deleted memory {memory_id} via tool call.")
                elif func_name == "update_memory":
                    memory_id = args.get("memory_id") # Get memory_id first
                    self.memory_db.update_memory(
                        memory_id, # Pass the variable
                        args.get("new_content"),
                        self.username
                    )
                    response_text = f"Successfully updated memory ID {memory_id}"
                    logger.info(f"[GeminiConnection-{self.username}] Updated memory {memory_id} via tool call.")
                else:
                    result = {"error": f"Unknown function {func_name}"}
                    response_text = f"Sorry, I don't know how to handle the function '{func_name}'."
                    logger.warning(f"[GeminiConnection-{self.username}] Unknown function call received: {func_name}")
            # End of the if/elif/else chain for function calls inside the try block
            except Exception as e: # This except block handles errors for the try block starting above
                logger.error(f"[GeminiConnection-{self.username}] Error executing tool function {func_name}: {e}", exc_info=True) # Log traceback
                result = {"error": f"Error executing function {func_name}: {str(e)}"}
                response_text = f"Sorry, there was an error trying to execute the function '{func_name}'."
            # This runs after the try-except block for the current function call 'f'

            responses.append({
                "id": f.get("id"),
                "name": func_name,
                "response": {
                    "name": func_name,
                    "content": result
                }
            })

            # Send a verbal response about the tool call result
            logger.info(f"[GeminiConnection-{self.username}] Sending verbal response for tool call {func_name}.")
            try:
                await self.ws.send(json.dumps({
                    "clientContent": {
                        "turns": [{
                            "parts": [{"text": response_text}],
                            "role": "user"
                        }],
                        "turnComplete": True
                    }
                }))
            except Exception as e:
                 logger.error(f"[GeminiConnection-{self.username}] Error sending tool call verbal response: {e}")
                 await self.close()
                 return # Stop processing further if send fails


        tool_response = {
            "toolResponse": {
                "functionResponses": responses
            }
        }
        logger.info(f"[GeminiConnection-{self.username}] Sending tool response: {tool_response}")
        try:
            await self.ws.send(json.dumps(tool_response))
        except Exception as e:
            logger.error(f"[GeminiConnection-{self.username}] Error sending tool response: {e}")
            await self.close()


    async def send_image(self, image_data: str):
        """Send image data to Gemini"""
        # Check Gemini connection state correctly
        if not self.ws or self.ws.state == State.CLOSED:
            logger.warning(f"[GeminiConnection-{self.username}] Attempted to send image while WebSocket is closed or None.")
            return

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
        try:
            await self.ws.send(json.dumps(image_message))
        except Exception as e:
            logger.error(f"[GeminiConnection-{self.username}] Error sending image data: {e}")
            await self.close()


# Helper function to get username from token
def get_username_from_token(token: str) -> str:
    """Extract username from JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return username
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Store active connections
connections: Dict[str, GeminiConnection] = {}
memory_db = MemoryDB()

@app.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_host = websocket.client.host
    client_port = websocket.client.port
    client_id = f"{client_host}:{client_port}"
    logger.info(f"[WebSocket-{client_id}] Connection attempt.")

    await websocket.accept()
    logger.info(f"[WebSocket-{client_id}] Connection accepted.")

    username = None
    gemini = None
    closed_intentionally = False # Flag to prevent double closing
    try:
        # Require authentication for WebSocket
        logger.info(f"[WebSocket-{client_id}] Attempting authentication.")
        username = await get_current_user_websocket(websocket)
        if not username:
            logger.warning(f"[WebSocket-{client_id}] Authentication failed. Preparing to close.")
            # Don't close here directly, let finally handle it.
            closed_intentionally = True # Mark intent to close
            return # Exit the try block
        logger.info(f"[WebSocket-{client_id}] Authenticated as user: {username}")

        gemini = GeminiConnection()
        gemini.username = username # Pass username to GeminiConnection
        connections[client_id] = gemini # Use client_id as key
        logger.info(f"[WebSocket-{client_id}] GeminiConnection created and stored for user {username}.")

        # Try to load saved config from database
        logger.info(f"[WebSocket-{client_id}] Attempting to load saved config for user {username}.")
        saved_config = memory_db.get_user_config(username)
        if saved_config:
            logger.info(f"[WebSocket-{client_id}] Loaded saved config for user {username}: {saved_config}")
        else:
            logger.info(f"[WebSocket-{client_id}] No saved config found for user {username}.")


        # Wait for initial configuration
        logger.info(f"[WebSocket-{client_id}] Waiting for initial configuration message.")
        config_data = await websocket.receive_json()
        logger.info(f"[WebSocket-{client_id}] Received initial message: {config_data}")

        if config_data.get("type") != "config":
            logger.error(f"[WebSocket-{client_id}] First message was not configuration type. Closing.")
            await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA, reason="First message must be configuration")
            raise ValueError("First message must be configuration")

        # Set the configuration and update it in the DB
        const_config = config_data.get("config", {})
        logger.info(f"[WebSocket-{client_id}] Processing initial config: {const_config}")

        # Ensure all required config fields are present
        default_config = {
            "systemPrompt": "You are a friendly AI assistant.",
            "voice": "Puck",
            "googleSearch": True,
            "allowInterruptions": True,
            "isWakeWordEnabled": False,
            "wakeWord": "",
            "cancelPhrase": ""
        }

        # Merge with defaults for any missing fields
        for key, value in default_config.items():
            if key not in const_config:
                const_config[key] = value
        gemini.set_config(const_config)
        memory_db.update_user_config(username, const_config) # Save initial config

        logger.info(f"[WebSocket-{client_id}] Initial config set and saved for user {username}.")

        # Initialize Gemini connection
        logger.info(f"[WebSocket-{client_id}] Initializing Gemini connection.")
        await gemini.connect()
        logger.info(f"[WebSocket-{client_id}] Gemini connection initialized successfully.")

        gemini_receive_task = None # Task handle for the Gemini receiver

        # Define receiver functions within the endpoint scope
        async def receive_from_gemini():
            nonlocal gemini_receive_task # To allow setting to None on exit
            try:
                while True:
                    # Check Gemini WebSocket state before receiving
                    if not gemini.ws or gemini.ws.state == State.CLOSED:
                         logger.warning(f"[GeminiReceiver-{client_id}] Gemini WebSocket is closed or None. Exiting loop.")
                         break

                    msg = await gemini.receive() # This now raises WebSocketDisconnect if Gemini closes
                    response = json.loads(msg)

                    if "toolCall" in response:
                        logger.info(f"[GeminiReceiver-{client_id}] Received tool call from Gemini.")
                        await gemini.handle_tool_call(response["toolCall"])
                        continue # Handled tool call, wait for next message

                    # Process server content
                    if "serverContent" in response:
                        content = response["serverContent"]
                        parts = []
                        if "modelTurn" in content:
                            parts = content["modelTurn"].get("parts", [])
                            # Store meaningful text responses from modelTurn
                            if any("text" in p for p in parts):
                                logger.info("[Memory] Storing modelTurn response")
                                try:
                                     memory_db.store_memory(
                                         content=json.dumps(content["modelTurn"]),
                                         username=username, # Ensure username is passed
                                         type="response"
                                     )
                                except Exception as db_err:
                                     logger.error(f"[Memory] Error storing response: {db_err}")

                        elif "candidates" in content:
                            # Assuming the first candidate is the one we want
                            candidate = content.get("candidates", [{}])[0]
                            parts = candidate.get("content", {}).get("parts", [])


                        # Forward parts (like audio) to the client
                        for p in parts:
                            # Check client connection state before sending
                            if websocket.client_state != WebSocketState.CONNECTED:
                                logger.warning(f"[GeminiReceiver-{client_id}] Client WebSocket disconnected before sending part. Aborting send.")
                                break # Stop sending parts if client disconnected

                            # If an interrupt was issued, skip sending any remaining audio chunks.
                            if gemini.interrupted:
                                logger.info(f"[GeminiReceiver-{client_id}] Interrupt active, skipping sending part.")
                                continue

                            if "inlineData" in p and "data" in p["inlineData"]:
                                data = p['inlineData']['data']
                                mime_type = p['inlineData'].get('mimeType', 'audio/pcm') # Default to audio if not specified
                                try:
                                    # Check client connection state again just before sending
                                    if websocket.client_state == WebSocketState.CONNECTED:
                                        await websocket.send_json({
                                            "type": mime_type.split('/')[0], # "audio" or "video" etc.
                                            "data": data
                                        })
                                    else:
                                        logger.warning(f"[GeminiReceiver-{client_id}] Client disconnected right before sending {mime_type} data.")
                                        break # Exit inner loop if client disconnected
                                except Exception as send_err:
                                     logger.error(f"[GeminiReceiver-{client_id}] Error sending data part to client: {send_err}")
                                     # If sending fails, assume client disconnected
                                     break # Stop trying to send parts

                            elif "text" in p:
                                # Text parts are not forwarded directly, but logged in GeminiConnection if needed
                                pass


                    # Handle turn completion
                    if response.get("serverContent", {}).get("turnComplete"):
                        if gemini.interrupted:
                             logger.info(f"[GeminiReceiver-{client_id}] Turn complete received, but interrupt was active. Resetting interrupt flag.")
                             gemini.interrupted = False # Reset interrupt flag after turn completion signal
                             gemini.interrupt_sent = False # Reset interrupt sent flag
                        else:
                            logger.info(f"[GeminiReceiver-{client_id}] Turn complete. Sending confirmation to client.")
                            try:
                                if websocket.client_state == WebSocketState.CONNECTED: # Check connection before sending
                                    await websocket.send_json({
                                        "type": "turn_complete",
                                        "data": True
                                    })
                            except Exception as send_err:
                                logger.error(f"[GeminiReceiver-{client_id}] Error sending turn_complete to client: {send_err}")
                                break # Assume client disconnected

                    # Check for interrupted response
                    if response.get("serverContent", {}).get("interrupted") is not None:
                        logger.info(f"[GeminiReceiver-{client_id}] Received interrupted signal from Gemini API.")
                        # Set the interrupted flag to ensure no more audio is sent
                        gemini.interrupted = True
                        try:
                            if websocket.client_state == WebSocketState.CONNECTED:
                                # Send interrupt confirmation to client
                                await websocket.send_json({
                                    "type": "interrupt_confirmed",
                                    "data": True
                                })
                                logger.info(f"[GeminiReceiver-{client_id}] Sent interrupt_confirmed to client.")

                                # Also send a stop_audio message to tell the client to stop playing any buffered audio
                                await websocket.send_json({
                                    "type": "stop_audio",
                                    "data": True
                                })
                                logger.info(f"[GeminiReceiver-{client_id}] Sent stop_audio to client.")
                        except Exception as send_err:
                            logger.error(f"[GeminiReceiver-{client_id}] Error sending interrupt_confirmed to client: {send_err}")

            except ws_exceptions.ConnectionClosedOK:
                logger.info(f"[GeminiReceiver-{client_id}] Gemini WebSocket closed cleanly (OK). Exiting loop.")
            except ws_exceptions.ConnectionClosedError as wse:
                logger.warning(f"[GeminiReceiver-{client_id}] Gemini WebSocket closed with error: {wse.code} - {wse.reason}. Exiting loop.")
            except WebSocketDisconnect as wsd:
                # This happens if gemini.receive() detects Gemini WS closed
                logger.info(f"[GeminiReceiver-{client_id}] Gemini WebSocket disconnected (WebSocketDisconnect): {wsd.code} - {wsd.reason}. Exiting loop.")
            except asyncio.CancelledError:
                 logger.info(f"[GeminiReceiver-{client_id}] Task cancelled.")
                 raise # Re-raise CancelledError so the awaiter knows
            except json.JSONDecodeError as e:
                logger.error(f"[GeminiReceiver-{client_id}] JSON decode error processing Gemini message: {e}. Message: {msg[:100]}...")
                # Continue might be risky if the connection is broken, maybe exit? For now, continue.
            except KeyError as e:
                logger.error(f"[GeminiReceiver-{client_id}] KeyError processing Gemini response: {e}. Response: {response}")
                # Continue might be risky.
            except Exception as e:
                logger.error(f"[GeminiReceiver-{client_id}] Unexpected error receiving/processing from Gemini: {type(e).__name__} - {str(e)}", exc_info=True)
                # Check if it's a disconnect-related error before deciding to break
                if "disconnect" in str(e).lower() or "connection closed" in str(e).lower():
                     logger.warning(f"[GeminiReceiver-{client_id}] Connection closed related error detected. Exiting loop.")
                # Exit loop on unexpected errors to prevent infinite loops
            finally:
                 logger.info(f"[GeminiReceiver-{client_id}] Exiting receive_from_gemini loop.")
                 # Ensure the task reference is cleared if the task exits itself
                 if gemini_receive_task is asyncio.current_task():
                     gemini_receive_task = None


        async def receive_from_client():
            nonlocal gemini_receive_task # Allow modification/restart
            while True:
                try:
                    # Check client connection state before receiving
                    if websocket.client_state != WebSocketState.CONNECTED:
                        logger.warning(f"[ClientReceiver-{client_id}] Client WebSocket is not connected ({websocket.client_state}). Exiting loop.")
                        break
                    message_text = await websocket.receive_text()

                    message_content = json.loads(message_text)
                    msg_type = message_content.get("type")
                    logger.info(f"[ClientReceiver-{client_id}] Received message type: {msg_type}")

                    if msg_type == "config":
                        # Handle config updates during active connection
                        logger.info(f"[ClientReceiver-{client_id}] Received updated config from client.")
                        updated_config = message_content.get("config", {})

                        # Ensure all required config fields are present
                        default_config = {
                            "systemPrompt": "You are a friendly AI assistant.",
                            "voice": "Puck",
                            "googleSearch": True,
                                "allowInterruptions": True,
                                "isWakeWordEnabled": False,
                                "wakeWord": "",
                            "cancelPhrase": ""
                        }

                        # Merge with defaults for any missing fields
                        for key, value in default_config.items():
                            if key not in updated_config:
                                updated_config[key] = value
                        # Update the configuration
                        gemini.set_config(updated_config)

                        # Save to database
                        memory_db.update_user_config(username, updated_config)
                        logger.info(f"[ClientReceiver-{client_id}] Updated config saved to database for user {username}")

                        # Reconnect to Gemini with new config, managing the receiver task
                        logger.info(f"[ClientReceiver-{client_id}] Reconnecting Gemini due to config change.")

                        # Cancel existing Gemini receiver task if it's running
                        if gemini_receive_task and not gemini_receive_task.done():
                            logger.info(f"[ClientReceiver-{client_id}] Cancelling existing Gemini receiver task.")
                            gemini_receive_task.cancel()
                            try:
                                await gemini_receive_task
                            except asyncio.CancelledError:
                                logger.info(f"[ClientReceiver-{client_id}] Existing Gemini receiver task cancelled.")
                            except Exception as task_cancel_err:
                                 logger.error(f"[ClientReceiver-{client_id}] Error awaiting cancelled Gemini task: {task_cancel_err}")
                            finally:
                                gemini_receive_task = None # Clear handle

                        # Perform the reconnect
                        await gemini.close()
                        await gemini.connect()
                        logger.info(f"[ClientReceiver-{client_id}] Gemini reconnected successfully.")

                        # Start a new Gemini receiver task
                        logger.info(f"[ClientReceiver-{client_id}] Starting new Gemini receiver task.")
                        gemini_receive_task = asyncio.create_task(receive_from_gemini())


                    elif msg_type == "audio":
                        if gemini.interrupted:
                                logger.info(f"[ClientReceiver-{client_id}] Audio received after interrupt, resuming generation.")
                                gemini.interrupted = False # Resume with a new generation if audio arrives after an interrupt

                        # Check Gemini connection state correctly
                        if not gemini.ws or gemini.ws.state == State.CLOSED:
                            logger.warning(f"[ClientReceiver-{client_id}] Gemini connection is closed. Attempting to reconnect before sending audio.")
                            try:
                                await gemini.connect()
                                logger.info(f"[ClientReceiver-{client_id}] Gemini reconnected successfully.")
                            except Exception as recon_err:
                                logger.error(f"[ClientReceiver-{client_id}] Failed to reconnect Gemini: {recon_err}. Skipping audio send.")
                                continue # Skip sending if reconnect fails
                        # Check Gemini connection state before sending audio
                        gemini_ws_state = gemini.ws.state if gemini.ws else 'None'
                        if gemini.ws and gemini_ws_state == State.OPEN:
                            try:
                                await gemini.send_audio(message_content["data"])
                            except Exception as send_audio_err:
                                logger.error(f"[ClientReceiver-{client_id}] Error calling gemini.send_audio: {send_audio_err}")
                        else:
                             logger.warning(f"[ClientReceiver-{client_id}] Skipping audio send because Gemini WS state is not OPEN (State: {gemini_ws_state}).")


                    elif msg_type == "image":
                       # Check Gemini connection state before sending image
                       gemini_ws_state = gemini.ws.state if gemini.ws else 'None'
                       if gemini.ws and gemini_ws_state == State.OPEN:
                           try:
                               await gemini.send_image(message_content["data"])
                           except Exception as send_image_err:
                               logger.error(f"[ClientReceiver-{client_id}] Error calling gemini.send_image: {send_image_err}")
                       else:
                            logger.warning(f"[ClientReceiver-{client_id}] Skipping image send because Gemini WS state is not OPEN (State: {gemini_ws_state}).")

                    elif msg_type == "interrupt":
                        logger.info(f"[ClientReceiver-{client_id}] Received interrupt command from client.")

                        # Send the interrupt signal to Gemini API
                        interrupt_success = await gemini.send_interrupt()

                        # Send confirmation to client
                        logger.info(f"[ClientReceiver-{client_id}] Sending interrupt confirmation to client.")
                        await websocket.send_json({
                            "type": "interrupt",
                            "message": "Generation canceled.",
                            "success": interrupt_success
                        })

                        # Also send a stop_audio message to tell the client to stop playing any buffered audio
                        await websocket.send_json({
                            "type": "stop_audio",
                            "data": True
                        })
                        logger.info(f"[ClientReceiver-{client_id}] Sent stop_audio to client.")
                        continue # Don't process further in this loop iteration

                    else:
                        logger.warning(f"[ClientReceiver-{client_id}] Unknown message type received: {msg_type}")

                except WebSocketDisconnect as wsd:
                    logger.info(f"[ClientReceiver-{client_id}] WebSocket disconnected: {wsd.code} - {wsd.reason}")
                    break # Exit loop on disconnect
                except json.JSONDecodeError as e:
                    logger.error(f"[ClientReceiver-{client_id}] JSON decode error: {e}. Message: {message_text[:100]}...")
                    continue # Skip malformed message
                except KeyError as e:
                    logger.error(f"[ClientReceiver-{client_id}] Key error in message: {e}. Message: {message_content}")
                    continue # Skip message with missing keys
                except Exception as e:
                    # Catch other potential errors during message processing
                    logger.error(f"[ClientReceiver-{client_id}] Error processing client message: {type(e).__name__} - {str(e)}")
                    # Check if it's a disconnect-related error before deciding to break
                    if "disconnect" in str(e).lower() or "connection closed" in str(e).lower():
                         logger.warning(f"[ClientReceiver-{client_id}] Connection closed related error detected. Exiting loop.")
                         break
                    continue # Continue processing other messages if possible

            logger.info(f"[ClientReceiver-{client_id}] Exiting receive_from_client loop.")


        # Start the initial Gemini receiver task
        logger.info(f"[WebSocket-{client_id}] Starting initial Gemini receiver task.")
        gemini_receive_task = asyncio.create_task(receive_from_gemini())

        # Run the client receiver loop in the main task
        logger.info(f"[WebSocket-{client_id}] Starting client receiver loop.")
        await receive_from_client() # This will run until the client disconnects

        logger.info(f"[WebSocket-{client_id}] Client receiver loop finished.")

    except WebSocketDisconnect as wsd:
         logger.info(f"[WebSocket-{client_id}] WebSocket disconnected: {wsd.code} - {wsd.reason}")
         closed_intentionally = True # Mark as closed on disconnect
    except Exception as e:
        logger.error(f"[WebSocket-{client_id}] Unexpected error in main WebSocket handler: {type(e).__name__} - {str(e)}", exc_info=True)
        # Attempt to close gracefully if possible
        if websocket.client_state == WebSocketState.CONNECTED:
             try:
                 await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Server error")
                 closed_intentionally = True # Mark as closed
             except RuntimeError: # Catch potential double-close error
                 logger.warning(f"[WebSocket-{client_id}] Error closing websocket in exception handler (already closing?).")
             except Exception as close_err:
                 logger.error(f"[WebSocket-{client_id}] Error closing websocket in exception handler: {close_err}")
    finally:
        # Cleanup
        logger.info(f"[WebSocket-{client_id}] Starting cleanup for connection.")

        # Cancel the Gemini receiver task if it's still running
        if gemini_receive_task and not gemini_receive_task.done():
             logger.info(f"[WebSocket-{client_id}] Cancelling Gemini receiver task during cleanup.")
             gemini_receive_task.cancel()
             try:
                 await gemini_receive_task
             except asyncio.CancelledError:
                 logger.info(f"[WebSocket-{client_id}] Gemini receiver task cancelled during cleanup.")
             except Exception as task_cancel_err:
                 # Log error, but continue cleanup
                 logger.error(f"[WebSocket-{client_id}] Error awaiting cancelled Gemini task during cleanup: {task_cancel_err}")

        # Close Gemini connection using the 'gemini' variable from the try block scope
        if gemini:
             logger.info(f"[WebSocket-{client_id}] Closing Gemini connection instance.")
             await gemini.close()
        # Remove from active connections dict (redundant if pop was used, but safe)
        if client_id in connections:
             del connections[client_id]
             logger.info(f"[WebSocket-{client_id}] Removed connection entry for {client_id}.")
        else:
             # This might happen if cleanup occurs after an error before connection was added
             logger.warning(f"[WebSocket-{client_id}] No connection entry found in dict for cleanup.")

        # Ensure client websocket is closed ONLY if it's still connected AND wasn't closed intentionally before
        if not closed_intentionally and websocket.client_state == WebSocketState.CONNECTED:
            logger.warning(f"[WebSocket-{client_id}] Client WebSocket state is CONNECTED, attempting close in finally.")
            try:
                await websocket.close(code=status.WS_1001_GOING_AWAY)
            except RuntimeError: # Catch potential double-close error here too
                logger.warning(f"[WebSocket-{client_id}] Error closing websocket in finally (already closing?).")
            except Exception as close_err:
                # Log error during close, but cleanup should continue
                logger.error(f"[WebSocket-{client_id}] Error during final WebSocket close: {close_err}")
        elif not closed_intentionally and websocket.client_state != WebSocketState.DISCONNECTED:
             # Log if state is unexpected (e.g., CONNECTING) but don't try to close
             logger.warning(f"[WebSocket-{client_id}] Client WebSocket in unexpected state {websocket.client_state} during cleanup (and not intentionally closed).")


        logger.info(f"[WebSocket-{client_id}] Cleanup complete. Connection fully closed.")

@app.get("/memories")
async def get_memories(request: Request):
    """Get all memories"""
    logger.info("Received request for /memories")
    try:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")

        if not token:
            logger.warning("Authentication token missing")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        username = get_username_from_token(token)
        logger.info(f"Fetching memories for user: {username}")
        memories = memory_db.get_all_memories(username)
        logger.info(f"Returning {len(memories)} memories for user {username}")
        return memories
    except HTTPException as he:
        logger.warning(f"HTTP Exception in /memories: {he.status_code} - {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in /memories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memories/{memory_id}")
async def get_memory(memory_id: int, request: Request):
    """Get a specific memory by ID"""
    logger.info(f"Received request for /memories/{memory_id}")
    try:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")

        if not token:
            logger.warning(f"Authentication token missing for /memories/{memory_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        username = get_username_from_token(token)
        logger.info(f"Fetching memory {memory_id} for user: {username}")

        # Get the memory and verify it belongs to the user
        memory = memory_db.get_memory(memory_id)
        if not memory:
            logger.warning(f"Memory {memory_id} not found for user {username}")
            raise HTTPException(status_code=404, detail="Memory not found")

        # Check if memory belongs to user (assuming memory[4] is username - adjust index if needed)
        # IMPORTANT: Ensure the index `4` correctly points to the username in your DB schema.
        memory_username_index = 4 # Adjust if your schema is different
        if len(memory) > memory_username_index and memory[memory_username_index] != username:
             logger.warning(f"User {username} attempted to access memory {memory_id} belonging to {memory[memory_username_index]}")
             raise HTTPException(status_code=403, detail="Not authorized to access this memory")

        logger.info(f"Returning memory {memory_id} for user {username}")
        return {
            "id": memory[0], # Assuming ID is at index 0
            "content": memory[1], # Assuming content is at index 1
            "timestamp": memory[2], # Assuming timestamp is at index 2
            "type": memory[3] # Assuming type is at index 3
        }
    except HTTPException as he:
        logger.warning(f"HTTP Exception in /memories/{memory_id}: {he.status_code} - {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in /memories/{memory_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/memories/{memory_id}")
async def delete_memory(memory_id: int, request: Request):
    """Delete a specific memory"""
    logger.info(f"Received request to delete /memories/{memory_id}")
    try:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")

        if not token:
            logger.warning(f"Authentication token missing for DELETE /memories/{memory_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        username = get_username_from_token(token)
        logger.info(f"Attempting to delete memory {memory_id} for user: {username}")
        # Assuming delete_memory handles authorization internally or raises an error
        memory_db.delete_memory(memory_id, username)
        logger.info(f"Successfully deleted memory {memory_id} for user {username}")
        return {"status": "success"}
    except HTTPException as he:
        logger.warning(f"HTTP Exception in DELETE /memories/{memory_id}: {he.status_code} - {he.detail}")
        raise he
    except Exception as e:
        # Catch potential errors from delete_memory (e.g., memory not found, auth error)
        logger.error(f"Error deleting memory {memory_id} for user {username}: {e}", exc_info=True)
        # You might want to return a more specific error code based on the exception type
        raise HTTPException(status_code=500, detail=f"Failed to delete memory: {str(e)}")

@app.post("/config")
async def update_config(request: Request):
    """Update user configuration"""
    logger.info("Received request to POST /config")
    try:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")

        if not token:
            logger.warning("Authentication token missing for POST /config")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        username = get_username_from_token(token)
        logger.info(f"Updating config for user: {username}")

        # Get the request body
        try:
            config_data = await request.json()
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON body for POST /config")
            raise HTTPException(status_code=400, detail="Invalid JSON format")


        # Ensure all required config fields are present
        default_config = {
            "systemPrompt": "You are a friendly AI assistant.",
            "voice": "Puck",
            "googleSearch": True,
            "allowInterruptions": True,
            "isWakeWordEnabled": False,
            "wakeWord": "",
            "cancelPhrase": ""
        }

        # Merge with defaults for any missing fields
        for key, value in default_config.items():
            if key not in config_data:
                config_data[key] = value
        # Update the configuration in the database
        try:
            memory_db.update_user_config(username, config_data)
            logger.info(f"Successfully updated config for user {username}")
        except Exception as db_err:
             logger.error(f"Database error updating config for user {username}: {db_err}", exc_info=True)
             raise HTTPException(status_code=500, detail="Database error updating configuration")


        return {"status": "success", "message": "Configuration updated successfully"}
    except HTTPException as he:
        logger.warning(f"HTTP Exception in POST /config: {he.status_code} - {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in POST /config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/config")
async def get_config(request: Request):
    """Get user configuration"""
    logger.info("Received request for GET /config")
    try:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")

        if not token:
            logger.warning("Authentication token missing for GET /config")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        username = get_username_from_token(token)
        logger.info(f"Fetching config for user: {username}")

        # Get the configuration from the database
        try:
            config = memory_db.get_user_config(username)
        except Exception as db_err:
            logger.error(f"Database error fetching config for user {username}: {db_err}", exc_info=True)
            raise HTTPException(status_code=500, detail="Database error fetching configuration")


        if not config:
            logger.info(f"No config found for user {username}, returning default.")
            # Return default config if none exists
            config = {
                "systemPrompt": "You are a friendly AI assistant.",
                "voice": "Puck",
                "googleSearch": True,
                "allowInterruptions": True,
                "isWakeWordEnabled": False,
                "wakeWord": "",
                "cancelPhrase": ""
            }
        else:
             logger.info(f"Returning saved config for user {username}")

        return config
    except HTTPException as he:
        logger.warning(f"HTTP Exception in GET /config: {he.status_code} - {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in GET /config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server...")
    # Consider adding reload=True for development, but remove for production
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
