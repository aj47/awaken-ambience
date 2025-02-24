import sqlite3
from datetime import datetime
import json

class MemoryDB:
    def __init__(self, db_path="memories.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    type TEXT NOT NULL
                )
            """)
            conn.commit()

    def store_memory(self, client_id: str, content: str, context: str = None, tags: list = None, type: str = "conversation"):
        """Stores a memory in the database.
        
        Args:
            client_id: The client identifier
            content: The main content of the memory
            context: Optional context about the memory
            tags: Optional list of tags to categorize the memory
            type: The type of memory (default: conversation)
        """
        print(f"[MemoryDB] Storing {type} memory for client {client_id[:8]}...")
        print(f"[MemoryDB] Content preview: {content[:100]}...")
        if context:
            print(f"[MemoryDB] Context: {context}")
        if tags:
            print(f"[MemoryDB] Tags: {', '.join(tags)}")
            
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO memories (client_id, content, type) VALUES (?, ?, ?)",
                (client_id, content, type)
            )
            conn.commit()
        print(f"[MemoryDB] Successfully stored memory")

    def get_all_memories(self, client_id: str):
        """Retrieves all memories for a client from the database.
        
        Args:
            client_id: The client identifier
        """
        print(f"[MemoryDB] Fetching all memories for client {client_id[:8]}...")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT content, timestamp FROM memories WHERE client_id = ? ORDER BY timestamp DESC",
                (client_id,)
            )
            memories = cursor.fetchall()
            print(f"[MemoryDB] Found {len(memories)} memories")
            for i, memory in enumerate(memories, 1):
                print(f"[MemoryDB] Memory {i}: {memory[0][:100]}... ({memory[1]})")
            return memories

    def get_recent_memories(self, client_id: str, limit: int = 5):
        """Retrieves recent memories from the database.
        
        Args:
            client_id: The client identifier
            limit: Maximum number of memories to retrieve
        """
        print(f"[MemoryDB] Fetching {limit} recent memories for client {client_id[:8]}...")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT content, timestamp FROM memories WHERE client_id = ? ORDER BY timestamp DESC LIMIT ?",
                (client_id, limit)
            )
            memories = cursor.fetchall()
            print(f"[MemoryDB] Found {len(memories)} memories")
            for i, memory in enumerate(memories, 1):
                print(f"[MemoryDB] Memory {i}: {memory[0][:100]}... ({memory[1]})")
            return memories

    def search_memories(self, client_id: str, query: str, limit: int = 5):
        """Searches memories by content.
        
        Args:
            client_id: The client identifier
            query: Search term to look for in memory content
            limit: Maximum number of results to return
        """
        print(f"[MemoryDB] Searching memories for client {client_id[:8]} with query: {query}")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT content, timestamp FROM memories WHERE client_id = ? AND content LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (client_id, f"%{query}%", limit)
            )
            memories = cursor.fetchall()
            print(f"[MemoryDB] Found {len(memories)} matching memories")
            for i, memory in enumerate(memories, 1):
                print(f"[MemoryDB] Match {i}: {memory[0][:100]}... ({memory[1]})")
            return memories

    def clear_memories(self, client_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM memories WHERE client_id = ?", (client_id,))
            conn.commit()
