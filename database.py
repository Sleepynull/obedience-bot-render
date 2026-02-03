import aiosqlite
import datetime
from typing import Optional, List, Dict, Any

DATABASE_NAME = "obedience.db"

async def init_db():
    """Initialize the database with required tables."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Users table - stores Discord user info and roles
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('dominant', 'submissive')),
                points INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Relationships table - maps dominants to submissives
        await db.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dominant_id INTEGER NOT NULL,
                submissive_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dominant_id) REFERENCES users(user_id),
                FOREIGN KEY (submissive_id) REFERENCES users(user_id),
                UNIQUE(dominant_id, submissive_id)
            )
        """)
        
        # Tasks table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submissive_id INTEGER NOT NULL,
                dominant_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                frequency TEXT NOT NULL CHECK(frequency IN ('daily', 'weekly')),
                point_value INTEGER DEFAULT 10,
                deadline TIMESTAMP,
                auto_reward_id INTEGER,
                auto_punishment_id INTEGER,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (submissive_id) REFERENCES users(user_id),
                FOREIGN KEY (dominant_id) REFERENCES users(user_id),
                FOREIGN KEY (auto_reward_id) REFERENCES rewards(id),
                FOREIGN KEY (auto_punishment_id) REFERENCES punishments(id)
            )
        """)
        
        # Task completions table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS task_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                submissive_id INTEGER NOT NULL,
                proof_url TEXT,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                points_earned INTEGER NOT NULL,
                approval_status TEXT DEFAULT 'pending' CHECK(approval_status IN ('pending', 'approved', 'rejected')),
                reviewed_by INTEGER,
                reviewed_at TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id),
                FOREIGN KEY (submissive_id) REFERENCES users(user_id),
                FOREIGN KEY (reviewed_by) REFERENCES users(user_id)
            )
        """)
        
        # Rewards table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dominant_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                point_cost INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dominant_id) REFERENCES users(user_id)
            )
        """)
        
        # Punishments table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS punishments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dominant_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dominant_id) REFERENCES users(user_id)
            )
        """)
        
        # Assigned rewards/punishments table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS assigned_rewards_punishments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submissive_id INTEGER NOT NULL,
                dominant_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('reward', 'punishment')),
                item_id INTEGER NOT NULL,
                reason TEXT,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (submissive_id) REFERENCES users(user_id),
                FOREIGN KEY (dominant_id) REFERENCES users(user_id)
            )
        """)
        
        await db.commit()

# User operations
async def register_user(user_id: int, username: str, role: str) -> bool:
    """Register a new user."""
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            await db.execute(
                "INSERT INTO users (user_id, username, role) VALUES (?, ?, ?)",
                (user_id, username, role)
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False

async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user information."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def update_points(user_id: int, points_delta: int) -> int:
    """Update user points and return new total."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute(
            "UPDATE users SET points = points + ? WHERE user_id = ?",
            (points_delta, user_id)
        )
        await db.commit()
        
        async with db.execute("SELECT points FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

# Relationship operations
async def create_relationship(dominant_id: int, submissive_id: int) -> bool:
    """Create a dominant-submissive relationship."""
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            await db.execute(
                "INSERT INTO relationships (dominant_id, submissive_id) VALUES (?, ?)",
                (dominant_id, submissive_id)
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False

async def get_submissives(dominant_id: int) -> List[Dict[str, Any]]:
    """Get all submissives for a dominant."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT u.* FROM users u
            JOIN relationships r ON u.user_id = r.submissive_id
            WHERE r.dominant_id = ?
        """, (dominant_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_dominant(submissive_id: int) -> Optional[Dict[str, Any]]:
    """Get the dominant for a submissive."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT u.* FROM users u
            JOIN relationships r ON u.user_id = r.dominant_id
            WHERE r.submissive_id = ?
        """, (submissive_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

# Task operations
async def create_task(submissive_id: int, dominant_id: int, title: str, 
                     description: str, frequency: str, point_value: int, deadline: datetime.datetime = None) -> int:
    """Create a new task."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO tasks (submissive_id, dominant_id, title, description, frequency, point_value, deadline)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (submissive_id, dominant_id, title, description, frequency, point_value, deadline))
        await db.commit()
        return cursor.lastrowid

async def get_tasks(submissive_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
    """Get all tasks for a submissive."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM tasks WHERE submissive_id = ?"
        if active_only:
            query += " AND active = 1"
        async with db.execute(query, (submissive_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def submit_task_completion(task_id: int, submissive_id: int, proof_url: str = None) -> Optional[int]:
    """Submit a task completion for approval and return completion ID."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Get task info
        async with db.execute("SELECT point_value FROM tasks WHERE id = ? AND active = 1", (task_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            points = row[0]
        
        # Record pending completion
        cursor = await db.execute("""
            INSERT INTO task_completions (task_id, submissive_id, proof_url, points_earned, approval_status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (task_id, submissive_id, proof_url, points))
        
        await db.commit()
        return cursor.lastrowid

async def approve_task_completion(completion_id: int, reviewer_id: int, approved: bool) -> Optional[int]:
    """Approve or reject a task completion. Returns points if approved."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Get completion info
        async with db.execute("""
            SELECT submissive_id, points_earned, approval_status FROM task_completions WHERE id = ?
        """, (completion_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[2] != 'pending':
                return None
            submissive_id, points, _ = row
        
        status = 'approved' if approved else 'rejected'
        
        # Update completion
        await db.execute("""
            UPDATE task_completions 
            SET approval_status = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, reviewer_id, completion_id))
        
        await db.commit()
        return points if approved else 0

async def get_pending_completions(dominant_id: int) -> List[Dict[str, Any]]:
    """Get all pending task completions for a dominant's submissives."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT tc.*, t.title, t.dominant_id, u.username as submissive_name
            FROM task_completions tc
            JOIN tasks t ON tc.task_id = t.id
            JOIN users u ON tc.submissive_id = u.user_id
            WHERE t.dominant_id = ? AND tc.approval_status = 'pending'
            ORDER BY tc.submitted_at ASC
        """, (dominant_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_expired_tasks() -> List[Dict[str, Any]]:
    """Get all tasks that have passed their deadline without completion."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT t.* FROM tasks t
            WHERE t.active = 1 
            AND t.deadline IS NOT NULL 
            AND t.deadline < CURRENT_TIMESTAMP
            AND NOT EXISTS (
                SELECT 1 FROM task_completions tc 
                WHERE tc.task_id = t.id 
                AND tc.approval_status = 'approved'
                AND tc.completed_at >= t.created_at
            )
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def deactivate_expired_task(task_id: int):
    """Mark a task as inactive after deadline expires."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("UPDATE tasks SET active = 0 WHERE id = ?", (task_id,))
        await db.commit()

async def get_task_stats(submissive_id: int, days: int = 7) -> Dict[str, Any]:
    """Get task completion statistics."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        since_date = datetime.datetime.now() - datetime.timedelta(days=days)
        
        # Total completions
        async with db.execute("""
            SELECT COUNT(*), SUM(points_earned) FROM task_completions
            WHERE submissive_id = ? AND completed_at >= ?
        """, (submissive_id, since_date)) as cursor:
            row = await cursor.fetchone()
            total_completions = row[0] or 0
            total_points = row[1] or 0
        
        # Completions by day
        async with db.execute("""
            SELECT DATE(completed_at) as date, COUNT(*) as count
            FROM task_completions
            WHERE submissive_id = ? AND completed_at >= ?
            GROUP BY DATE(completed_at)
            ORDER BY date
        """, (submissive_id, since_date)) as cursor:
            daily_stats = await cursor.fetchall()
        
        return {
            'total_completions': total_completions,
            'total_points': total_points,
            'daily_stats': [{'date': row[0], 'count': row[1]} for row in daily_stats]
        }

# Reward operations
async def create_reward(dominant_id: int, title: str, description: str, point_cost: int) -> int:
    """Create a new reward."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO rewards (dominant_id, title, description, point_cost)
            VALUES (?, ?, ?, ?)
        """, (dominant_id, title, description, point_cost))
        await db.commit()
        return cursor.lastrowid

async def get_rewards(dominant_id: int) -> List[Dict[str, Any]]:
    """Get all rewards for a dominant."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM rewards WHERE dominant_id = ?", (dominant_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def assign_reward(submissive_id: int, dominant_id: int, reward_id: int, reason: str = None) -> bool:
    """Assign a reward to a submissive."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("""
            INSERT INTO assigned_rewards_punishments (submissive_id, dominant_id, type, item_id, reason)
            VALUES (?, ?, 'reward', ?, ?)
        """, (submissive_id, dominant_id, reward_id, reason))
        await db.commit()
        return True

# Punishment operations
async def create_punishment(dominant_id: int, title: str, description: str) -> int:
    """Create a new punishment."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO punishments (dominant_id, title, description)
            VALUES (?, ?, ?)
        """, (dominant_id, title, description))
        await db.commit()
        return cursor.lastrowid

async def get_punishments(dominant_id: int) -> List[Dict[str, Any]]:
    """Get all punishments for a dominant."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM punishments WHERE dominant_id = ?", (dominant_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def assign_punishment(submissive_id: int, dominant_id: int, punishment_id: int, reason: str = None) -> bool:
    """Assign a punishment to a submissive."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("""
            INSERT INTO assigned_rewards_punishments (submissive_id, dominant_id, type, item_id, reason)
            VALUES (?, ?, 'punishment', ?, ?)
        """, (submissive_id, dominant_id, punishment_id, reason))
        await db.commit()
        return True

async def get_assigned_items(submissive_id: int, item_type: str = None) -> List[Dict[str, Any]]:
    """Get assigned rewards or punishments for a submissive."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM assigned_rewards_punishments WHERE submissive_id = ?"
        params = [submissive_id]
        
        if item_type:
            query += " AND type = ?"
            params.append(item_type)
        
        query += " ORDER BY assigned_at DESC LIMIT 10"
        
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
