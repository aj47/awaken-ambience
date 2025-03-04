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
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    type TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def store_memory(self, content: str, type: str = "conversation", context: str = None, tags: list = None):
        """Stores a memory in the database.
        
        Args:
            content: The main content of the memory
            type: The type of memory (default: conversation)
            context: Optional context about the memory
            tags: Optional list of tags to categorize the memory
        """
        print(f"[MemoryDB] Storing {type} memory...")
        print(f"[MemoryDB] Content preview: {content[:100]}...")
        if context:
            print(f"[MemoryDB] Context: {context}")
        if tags:
            print(f"[MemoryDB] Tags: {', '.join(tags)}")
            
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO memories (content, type) VALUES (?, ?)",
                (content, type)
            )
            conn.commit()
        print(f"[MemoryDB] Successfully stored memory")

    def get_all_memories(self, client_id=None):
        """Retrieves all memories from the database.
        
        Args:
            client_id: Optional client identifier to filter memories
        """
        print(f"[MemoryDB] Fetching all memories for client {client_id or 'all'}...")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row  # Return rows as dictionaries
            cursor = conn.execute(
                "SELECT id, content, timestamp, type FROM memories ORDER BY timestamp DESC"
            )
            memories = cursor.fetchall()
            print(f"[MemoryDB] Found {len(memories)} memories")
            for i, memory in enumerate(memories, 1):
                print(f"[MemoryDB] Memory {i}: {memory['content'][:100]}... ({memory['timestamp']})")
            return [dict(memory) for memory in memories]  # Convert to list of dictionaries

    def get_recent_memories(self, limit: int = 5):
        """Retrieves recent memories from the database.
        
        Args:
            limit: Maximum number of memories to retrieve
        """
        print(f"[MemoryDB] Fetching {limit} recent memories...")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT content, timestamp FROM memories ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            memories = cursor.fetchall()
            print(f"[MemoryDB] Found {len(memories)} memories")
            for i, memory in enumerate(memories, 1):
                print(f"[MemoryDB] Memory {i}: {memory[0][:100]}... ({memory[1]})")
            return memories

    def search_memories(self, query: str, limit: int = 5):
        """Searches memories by content.
        
        Args:
            query: Search term to look for in memory content
            limit: Maximum number of results to return
        """
        print(f"[MemoryDB] Searching memories with query: {query}")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT content, timestamp FROM memories WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (f"%{query}%", limit)
            )
            memories = cursor.fetchall()
            print(f"[MemoryDB] Found {len(memories)} matching memories")
            for i, memory in enumerate(memories, 1):
                print(f"[MemoryDB] Match {i}: {memory[0][:100]}... ({memory[1]})")
            return memories

    def clear_memories(self):
        """Clears all memories"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM memories")
            conn.commit()
            print("[MemoryDB] Cleared all memories")

    def delete_memory(self, memory_id: int):
        """Deletes a specific memory by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            print(f"[MemoryDB] Deleted memory ID {memory_id}")

    def update_memory(self, memory_id: int, new_content: str):
        """Updates the content of a specific memory"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE memories SET content = ? WHERE id = ?",
                (new_content, memory_id)
            )
            conn.commit()
            print(f"[MemoryDB] Updated memory ID {memory_id}")
    def create_user(self, username: str, password: str):
        """Creates a new user with hashed password"""
        hashed_password = get_password_hash(password)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
                (username, hashed_password)
            )
            conn.commit()
        print(f"[MemoryDB] Created user {username}")

    def get_user(self, username: str):
        """Get user by username"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT username, hashed_password FROM users WHERE username = ?",
                (username,)
            )
            user = cursor.fetchone()
            return user

    def get_memory(self, memory_id: int):
        """Retrieves a specific memory by ID.
        
        Args:
            memory_id: The ID of the memory to retrieve
        """
        print(f"[MemoryDB] Fetching memory ID {memory_id}...")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, content, timestamp, type FROM memories WHERE id = ?",
                (memory_id,)
            )
            memory = cursor.fetchone()
            if memory:
                print(f"[MemoryDB] Found memory: {memory[1][:100]}...")
            else:
                print(f"[MemoryDB] Memory ID {memory_id} not found")
            return memory
