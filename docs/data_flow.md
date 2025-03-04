sequenceDiagram
  participant FE as Frontend (Browser)
  participant BE as Backend (FastAPI)
  participant Gemini as Gemini API
  participant DB as Database (SQLite)
  participant LS as Local Storage

  %% Configuration Flow
  FE->>LS: Load config from Local Storage
  LS-->>FE: Config data
  FE->>BE: WebSocket connection & Config data
  BE->>Gemini: Setup message (with system prompt & memories)
  Gemini-->>BE: Setup response

  %% Audio/Image Flow
  FE->>BE: Audio/Image data (via WebSocket)
  BE->>Gemini: Audio/Image data
  Gemini-->>BE: Audio response
  BE->>FE: Audio response (via WebSocket)

  %% Memory Storage Flow
  BE->>Gemini: Tool Call (store_memory)
  Gemini-->>BE: Function call details
  BE->>DB: Store memory
  DB-->>BE: Confirmation

  %% Memory Retrieval Flow
  BE->>DB: Get memories
  DB-->>BE: Memories data
  BE->>Gemini: Setup message (with memories)

  %% Interrupt Flow
  FE->>BE: Interrupt signal (via WebSocket)
  BE->>Gemini: N/A (Interrupt handled locally)
  BE->>FE: Interrupt confirmation
