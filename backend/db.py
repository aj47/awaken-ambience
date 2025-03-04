import sqlite3
from datetime import datetime
import json
from security import get_password_hash

class MemoryDB:
    def __init__(self, db_path="memories.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            # Create memories table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    type TEXT NOT NULL,
                    username TEXT NOT NULL
                )""")
            
            # Create users table – add config column to store JSON config
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    config TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )""")
            conn.commit()
            self.create_default_user()

    def create_default_user(self):
        """Creates a default admin user if it doesn't exist."""
        default_username = "admin"
        default_password = "admin"
        default_config = {
            "systemPrompt": "You are a friendly AI assistant.",
            "voice": "Puck",
            "googleSearch": True,
            "allowInterruptions": True,
            "isWakeWordEnabled": False,
            "wakeWord": "",
            "cancelPhrase": ""
        }

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT username FROM users WHERE username = ?",
                (default_username,)
            )
            if cursor.fetchone() is None:
                self.create_user(default_username, default_password)
                self.update_user_config(default_username, default_config)
                print(f"[MemoryDB] Created default user: {default_username}")

    def store_memory(self, content: str, username: str, type: str = "conversation", context: str = None, tags: list = None):
        """Stores a memory in the database.

        Args:
            content: The main content of the memory
            username: The user associated
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
                "INSERT INTO memories (content, type, username) VALUES (?, ?, ?)",
                (content, type, username)
            )
            conn.commit()
        print(f"[MemoryDB] Successfully stored memory")

    def get_all_memories(self, username: str):
        """Retrieves all memories from the database.
        
        Args:
            username: User identifier to filter memories
        """
        print(f"[MemoryDB] Fetching all memories for user {username}...")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, content, timestamp, type FROM memories WHERE username = ? ORDER BY timestamp DESC",
                (username,)
            )
            memories = cursor.fetchall()
            return [dict(memory) for memory in memories]

    def get_recent_memories(self, username: str, limit: int = 5):
        """Retrieves recent memories from the database.
        
        Args:
            username: User
            limit: Maximum number of memories to retrieve
        """
        print(f"[MemoryDB] Fetching {limit} recent memories...")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT content, timestamp FROM memories WHERE username = ? ORDER BY timestamp DESC LIMIT ?",
                (username, limit)
            )
            memories = cursor.fetchall()
            return memories

    def search_memories(self, username: str, query: str, limit: int = 5):
        """Searches memories by content.
        
        Args:
            username: User
            query: Search term to look for in memory content
            limit: Maximum number of results to return
        """
        print(f"[MemoryDB] Searching memories with query: {query}")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT content, timestamp FROM memories WHERE username = ? AND content LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (username, f"%{query}%", limit)
            )
            memories = cursor.fetchall()
            return memories

    def clear_memories(self):
        """Clears all memories"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM memories")
            conn.commit()
            print("[MemoryDB] Cleared all memories")

    def delete_memory(self, memory_id: int, username: str):
        """Deletes a specific memory by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM memories WHERE id = ? AND username = ?", (memory_id, username))
            conn.commit()

    def update_memory(self, memory_id: int, new_content: str, username: str):
        """Updates the content of a specific memory"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE memories SET content = ? WHERE id = ? AND username = ?",
                (new_content, memory_id, username)
            )
            conn.commit()
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

    def update_user_config(self, username: str, config: dict):
        """Update the configuration for a user."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET config = ? WHERE username = ?",
                (json.dumps(config), username)
            )
            conn.commit()
        print(f"[MemoryDB] Updated config for user {username}")

    def get_user_config(self, username: str):
        """Retrieve a user’s configuration."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT config FROM users WHERE username = ?",
                (username,)
            )
            row = cursor.fetchone()
            if row and row[0]:
                try:
                    return json.loads(row[0])
                except Exception as e:
                    print(f"[MemoryDB] Error parsing config for user {username}: {e}")
            return None
