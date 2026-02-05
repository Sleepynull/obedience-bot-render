import aiosqlite
import datetime
import pytz
import os
from typing import Optional, List, Dict, Any

# Use persistent storage path if available (for Render.com deployment)
# Otherwise use local directory for development
DATA_DIR = os.environ.get('DATA_DIR', '/data') if os.path.exists('/data') else '.'
DATABASE_NAME = os.path.join(DATA_DIR, "obedience.db")

print(f"Using database path: {DATABASE_NAME}")

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
                timezone TEXT DEFAULT 'UTC',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Add timezone column if it doesn't exist (migration)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT 'UTC'")
            await db.commit()
        except:
            pass  # Column already exists
        
        # Add deadline_time column to tasks if it doesn't exist (migration)
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN deadline_time TEXT")
            await db.commit()
        except:
            pass  # Column already exists
        
        # Add reminder columns to tasks if they don't exist (migration)
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN reminder_interval_hours INTEGER")
            await db.commit()
        except:
            pass  # Column already exists
        
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN last_reminder_sent TIMESTAMP")
            await db.commit()
        except:
            pass  # Column already exists
        
        # Add reminder columns to assigned_rewards_punishments if they don't exist (migration)
        try:
            await db.execute("ALTER TABLE assigned_rewards_punishments ADD COLUMN reminder_interval_hours INTEGER")
            await db.commit()
        except:
            pass  # Column already exists
        
        try:
            await db.execute("ALTER TABLE assigned_rewards_punishments ADD COLUMN last_reminder_sent TIMESTAMP")
            await db.commit()
        except:
            pass  # Column already exists
        
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
                frequency TEXT NOT NULL CHECK(frequency IN ('daily', 'weekly', 'custom')),
                point_value INTEGER DEFAULT 10,
                deadline TIMESTAMP,
                deadline_time TEXT,
                recurrence_enabled INTEGER DEFAULT 0,
                recurrence_interval_hours INTEGER,
                days_of_week TEXT,
                time_of_day TEXT,
                last_reset_at TIMESTAMP,
                next_occurrence TIMESTAMP,
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
                FOREIGN KEY (dominant_id) REFERENCES users(user_id),
                UNIQUE(dominant_id, title)
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
                FOREIGN KEY (dominant_id) REFERENCES users(user_id),
                UNIQUE(dominant_id, title)
            )
        """)
        
        # Point threshold triggers table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS point_thresholds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dominant_id INTEGER NOT NULL,
                submissive_id INTEGER,
                threshold_points INTEGER NOT NULL,
                punishment_id INTEGER NOT NULL,
                active INTEGER DEFAULT 1,
                last_triggered_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dominant_id) REFERENCES users(user_id),
                FOREIGN KEY (submissive_id) REFERENCES users(user_id),
                FOREIGN KEY (punishment_id) REFERENCES punishments(id)
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
                deadline TIMESTAMP,
                point_penalty INTEGER DEFAULT 0,
                proof_url TEXT,
                forward_to_user_id INTEGER,
                completion_status TEXT DEFAULT 'pending' CHECK(completion_status IN ('pending', 'submitted', 'approved', 'rejected', 'expired')),
                submitted_at TIMESTAMP,
                reviewed_by INTEGER,
                reviewed_at TIMESTAMP,
                FOREIGN KEY (submissive_id) REFERENCES users(user_id),
                FOREIGN KEY (dominant_id) REFERENCES users(user_id),
                FOREIGN KEY (reviewed_by) REFERENCES users(user_id)
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

async def set_user_timezone(user_id: int, timezone: str) -> bool:
    """Set user's timezone preference."""
    # Validate timezone
    try:
        pytz.timezone(timezone)
    except pytz.UnknownTimeZoneError:
        return False
    
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute(
            "UPDATE users SET timezone = ? WHERE user_id = ?",
            (timezone, user_id)
        )
        await db.commit()
    return True

async def get_user_timezone(user_id: int) -> str:
    """Get user's timezone preference, defaults to UTC."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        async with db.execute("SELECT timezone FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else 'UTC'

def get_user_time_now(timezone_str: str = 'UTC') -> datetime.datetime:
    """Get current time in user's timezone."""
    tz = pytz.timezone(timezone_str)
    return datetime.datetime.now(tz)

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
    """Get the dominant for a submissive (returns first if multiple exist)."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT u.* FROM users u
            JOIN relationships r ON u.user_id = r.dominant_id
            WHERE r.submissive_id = ?
        """, (submissive_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_dominants(submissive_id: int) -> List[Dict[str, Any]]:
    """Get all dominants for a submissive."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT u.* FROM users u
            JOIN relationships r ON u.user_id = r.dominant_id
            WHERE r.submissive_id = ?
        """, (submissive_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_next_available_id(db, table: str) -> int:
    """Find the lowest available ID in a table (reuses deleted IDs)."""
    # Get the max ID first
    async with db.execute(f"SELECT MAX(id) FROM {table}") as cursor:
        row = await cursor.fetchone()
        max_id = row[0] if row[0] else 0
    
    # Find gaps in the ID sequence
    for potential_id in range(1, max_id + 2):
        async with db.execute(f"SELECT id FROM {table} WHERE id = ?", (potential_id,)) as cursor:
            if not await cursor.fetchone():
                return potential_id
    
    return max_id + 1

# Task operations
async def create_task(submissive_id: int, dominant_id: int, title: str, 
                     description: str, frequency: str, point_value: int, deadline: datetime.datetime = None,
                     recurrence_enabled: bool = False, recurrence_interval_hours: int = None,
                     days_of_week: str = None, time_of_day: str = None, auto_punishment_id: int = None,
                     deadline_time: str = None, reminder_interval_hours: int = None) -> int:
    """Create a new task with optional recurring schedule, auto-punishment, and reminders."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Calculate next occurrence if recurring
        next_occurrence = None
        if recurrence_enabled and (days_of_week or recurrence_interval_hours):
            next_occurrence = calculate_next_occurrence(days_of_week, time_of_day, recurrence_interval_hours)
        
        # Get next available ID
        next_id = await get_next_available_id(db, 'tasks')
        
        await db.execute("""
            INSERT INTO tasks (
                id, submissive_id, dominant_id, title, description, frequency, point_value, deadline, deadline_time,
                recurrence_enabled, recurrence_interval_hours, days_of_week, time_of_day, next_occurrence, auto_punishment_id, reminder_interval_hours
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (next_id, submissive_id, dominant_id, title, description, frequency, point_value, deadline, deadline_time,
              recurrence_enabled, recurrence_interval_hours, days_of_week, time_of_day, next_occurrence, auto_punishment_id, reminder_interval_hours))
        await db.commit()
        return next_id

def calculate_next_occurrence(days_of_week: str = None, time_of_day: str = None, 
                             interval_hours: int = None) -> datetime.datetime:
    """Calculate the next occurrence of a recurring task."""
    now = datetime.datetime.now()
    
    if interval_hours:
        # Simple interval-based recurrence
        return now + datetime.timedelta(hours=interval_hours)
    
    if days_of_week:
        # Day-of-week based recurrence (format: "0,2,4" for Mon/Wed/Fri)
        target_days = [int(d) for d in days_of_week.split(',')]
        current_day = now.weekday()
        
        # Find next occurrence
        for days_ahead in range(1, 8):
            future_date = now + datetime.timedelta(days=days_ahead)
            if future_date.weekday() in target_days:
                # Set time if specified
                if time_of_day:
                    hour, minute = map(int, time_of_day.split(':'))
                    return future_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                return future_date
    
    # Default: 24 hours from now
    return now + datetime.timedelta(hours=24)

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

async def approve_task_completion(completion_id: int, reviewer_id: int, approved: bool, 
                                  reset_deadline_on_reject: bool = False) -> Optional[int]:
    """Approve or reject a task completion. Returns points if approved."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Get completion info and associated task
        async with db.execute("""
            SELECT tc.submissive_id, tc.points_earned, tc.approval_status, tc.task_id,
                   t.deadline_time, t.submissive_id as task_submissive_id
            FROM task_completions tc
            JOIN tasks t ON tc.task_id = t.id
            WHERE tc.id = ?
        """, (completion_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[2] != 'pending':
                return None
            submissive_id, points, _, task_id, deadline_time, task_submissive_id = row
        
        status = 'approved' if approved else 'rejected'
        
        # Update completion
        await db.execute("""
            UPDATE task_completions 
            SET approval_status = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, reviewer_id, completion_id))
        
        # Handle deadline reset for both approval and reject_cancel
        should_reset_deadline = (approved or reset_deadline_on_reject) and deadline_time
        
        if should_reset_deadline:
            # Get submissive's timezone
            sub_timezone = await get_user_timezone(task_submissive_id)
            user_tz = pytz.timezone(sub_timezone)
            
            # Calculate next deadline
            try:
                time_parts = deadline_time.split(':')
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                
                # Get current time in user's timezone
                now = datetime.datetime.now(user_tz)
                new_deadline = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                # If time has already passed today, set for tomorrow
                if new_deadline <= now:
                    new_deadline = new_deadline + datetime.timedelta(days=1)
                
                # Reset deadline and reactivate task
                await db.execute("""
                    UPDATE tasks 
                    SET deadline = ?, active = 1
                    WHERE id = ?
                """, (new_deadline, task_id))
            except (ValueError, IndexError):
                # If there's an issue parsing deadline_time, just continue without resetting
                pass
        
        await db.commit()
        return points if approved else 0

async def assign_punishment_for_rejected_task(task_id: int, submissive_id: int, dominant_id: int) -> Optional[int]:
    """Assign punishment when task is rejected. Uses auto_punishment_id if set, otherwise random."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Get task's auto_punishment_id
        async with db.execute(
            "SELECT auto_punishment_id FROM tasks WHERE id = ?",
            (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            auto_punishment_id = row[0]
        
        # Determine which punishment to assign
        punishment_id = None
        if auto_punishment_id and auto_punishment_id != -1:
            # Use the specific linked punishment
            punishment_id = auto_punishment_id
        elif auto_punishment_id == -1:
            # Random punishment flag
            random_punishment = await get_random_punishment(dominant_id)
            if random_punishment:
                punishment_id = random_punishment['id']
        else:
            # No auto_punishment configured, use random
            random_punishment = await get_random_punishment(dominant_id)
            if random_punishment:
                punishment_id = random_punishment['id']
        
        if not punishment_id:
            return None
        
        # Get submissive's timezone for deadline calculation
        sub_timezone = await get_user_timezone(submissive_id)
        user_tz = pytz.timezone(sub_timezone)
        
        # Set punishment deadline to 24 hours from now in user's timezone
        deadline = datetime.datetime.now(user_tz) + datetime.timedelta(hours=24)
        
        # Assign punishment
        assignment_id = await assign_punishment(
            submissive_id,
            dominant_id,
            punishment_id,
            reason="Task submission rejected",
            deadline=deadline,
            point_penalty=10
        )
        
        return assignment_id

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

async def get_tasks_to_reset() -> List[Dict[str, Any]]:
    """Get recurring tasks that need to be reset."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT t.* FROM tasks t
            WHERE t.recurrence_enabled = 1
            AND t.active = 1
            AND t.next_occurrence IS NOT NULL
            AND t.next_occurrence <= CURRENT_TIMESTAMP
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def reset_recurring_task(task_id: int, days_of_week: str = None, time_of_day: str = None, 
                              interval_hours: int = None):
    """Reset a recurring task and calculate next occurrence."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        next_occurrence = calculate_next_occurrence(days_of_week, time_of_day, interval_hours)
        
        # Clear any pending completions for this task
        await db.execute("""
            DELETE FROM task_completions 
            WHERE task_id = ? AND approval_status = 'pending'
        """, (task_id,))
        
        # Update task with new occurrence time
        await db.execute("""
            UPDATE tasks 
            SET last_reset_at = CURRENT_TIMESTAMP, next_occurrence = ?
            WHERE id = ?
        """, (next_occurrence, task_id))
        
        await db.commit()

async def delete_task(task_id: int, dominant_id: int) -> bool:
    """Delete a task (dominant only)."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Verify dominant owns this task
        async with db.execute("SELECT id FROM tasks WHERE id = ? AND dominant_id = ?", (task_id, dominant_id)) as cursor:
            if not await cursor.fetchone():
                return False
        
        # Delete associated completions first
        await db.execute("DELETE FROM task_completions WHERE task_id = ?", (task_id,))
        
        # Delete task
        await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.commit()
        return True

async def edit_task(task_id: int, dominant_id: int, title: str = None, description: str = None, 
                   point_value: int = None, deadline: datetime.datetime = None, reminder_interval_hours: int = None) -> bool:
    """Edit a task (dominant only). Only updates provided fields."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Verify dominant owns this task
        async with db.execute("SELECT id FROM tasks WHERE id = ? AND dominant_id = ?", (task_id, dominant_id)) as cursor:
            if not await cursor.fetchone():
                return False
        
        # Build update query dynamically
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if point_value is not None:
            updates.append("point_value = ?")
            params.append(point_value)
        if deadline is not None:
            updates.append("deadline = ?")
            params.append(deadline)
        if reminder_interval_hours is not None:
            updates.append("reminder_interval_hours = ?")
            params.append(reminder_interval_hours)
        
        if not updates:
            return True  # Nothing to update
        
        params.append(task_id)
        query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
        
        await db.execute(query, params)
        await db.commit()
        return True

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
        # Get next available ID
        next_id = await get_next_available_id(db, 'rewards')
        
        await db.execute("""
            INSERT INTO rewards (id, dominant_id, title, description, point_cost)
            VALUES (?, ?, ?, ?, ?)
        """, (next_id, dominant_id, title, description, point_cost))
        await db.commit()
        return next_id

async def get_rewards(dominant_id: int) -> List[Dict[str, Any]]:
    """Get all rewards for a dominant."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM rewards WHERE dominant_id = ?", (dominant_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def delete_reward(reward_id: int, dominant_id: int) -> bool:
    """Delete a reward (dominant only)."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Verify dominant owns this reward
        async with db.execute("SELECT id FROM rewards WHERE id = ? AND dominant_id = ?", (reward_id, dominant_id)) as cursor:
            if not await cursor.fetchone():
                return False
        
        # Delete reward assignments first
        await db.execute("DELETE FROM assigned_rewards_punishments WHERE type = 'reward' AND item_id = ?", (reward_id,))
        
        # Delete reward
        await db.execute("DELETE FROM rewards WHERE id = ?", (reward_id,))
        await db.commit()
        return True

async def edit_reward(reward_id: int, dominant_id: int, title: str = None, 
                     description: str = None, point_cost: int = None) -> bool:
    """Edit a reward (dominant only). Only updates provided fields."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Verify dominant owns this reward
        async with db.execute("SELECT id FROM rewards WHERE id = ? AND dominant_id = ?", (reward_id, dominant_id)) as cursor:
            if not await cursor.fetchone():
                return False
        
        # Build update query dynamically
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if point_cost is not None:
            updates.append("point_cost = ?")
            params.append(point_cost)
        
        if not updates:
            return True  # Nothing to update
        
        params.append(reward_id)
        query = f"UPDATE rewards SET {', '.join(updates)} WHERE id = ?"
        
        await db.execute(query, params)
        await db.commit()
        return True

async def get_affordable_rewards(submissive_id: int, current_points: int) -> List[Dict[str, Any]]:
    """Get rewards the submissive can now afford but couldn't before."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        # Get dominant for this submissive
        async with db.execute("""
            SELECT dominant_id FROM relationships WHERE submissive_id = ?
        """, (submissive_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return []
            dominant_id = row[0]
        
        # Get rewards they can afford
        async with db.execute("""
            SELECT * FROM rewards 
            WHERE dominant_id = ? AND point_cost > 0 AND point_cost <= ?
            ORDER BY point_cost ASC
        """, (dominant_id, current_points)) as cursor:
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
        # Get next available ID
        next_id = await get_next_available_id(db, 'punishments')
        
        await db.execute("""
            INSERT INTO punishments (id, dominant_id, title, description)
            VALUES (?, ?, ?, ?)
        """, (next_id, dominant_id, title, description))
        await db.commit()
        return next_id

async def delete_punishment(punishment_id: int, dominant_id: int) -> bool:
    """Delete a punishment (dominant only)."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Verify dominant owns this punishment
        async with db.execute("SELECT id FROM punishments WHERE id = ? AND dominant_id = ?", (punishment_id, dominant_id)) as cursor:
            if not await cursor.fetchone():
                return False
        
        # Delete punishment assignments first
        await db.execute("DELETE FROM assigned_rewards_punishments WHERE type = 'punishment' AND item_id = ?", (punishment_id,))
        
        # Delete punishment
        await db.execute("DELETE FROM punishments WHERE id = ?", (punishment_id,))
        await db.commit()
        return True

async def edit_punishment(punishment_id: int, dominant_id: int, title: str = None, 
                         description: str = None) -> bool:
    """Edit a punishment (dominant only). Only updates provided fields."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Verify dominant owns this punishment
        async with db.execute("SELECT id FROM punishments WHERE id = ? AND dominant_id = ?", (punishment_id, dominant_id)) as cursor:
            if not await cursor.fetchone():
                return False
        
        # Build update query dynamically
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        
        if not updates:
            return True  # Nothing to update
        
        params.append(punishment_id)
        query = f"UPDATE punishments SET {', '.join(updates)} WHERE id = ?"
        
        await db.execute(query, params)
        await db.commit()
        return True

async def get_punishments(dominant_id: int) -> List[Dict[str, Any]]:
    """Get all punishments for a dominant."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM punishments WHERE dominant_id = ?", (dominant_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def assign_punishment(submissive_id: int, dominant_id: int, punishment_id: int, 
                          reason: str = None, deadline: datetime.datetime = None, point_penalty: int = 10,
                          forward_to_user_id: int = None, reminder_interval_hours: int = None) -> int:
    """Assign a punishment to a submissive with deadline, point penalty, and optional reminders."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO assigned_rewards_punishments 
            (submissive_id, dominant_id, type, item_id, reason, deadline, point_penalty, forward_to_user_id, completion_status, reminder_interval_hours)
            VALUES (?, ?, 'punishment', ?, ?, ?, ?, ?, 'pending', ?)
        """, (submissive_id, dominant_id, punishment_id, reason, deadline, point_penalty, forward_to_user_id, reminder_interval_hours))
        await db.commit()
        return cursor.lastrowid

async def get_punishment_forward_user(assignment_id: int) -> Optional[int]:
    """Get the forward_to_user_id for a punishment assignment."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        async with db.execute(
            "SELECT forward_to_user_id FROM assigned_rewards_punishments WHERE id = ? AND type = 'punishment'",
            (assignment_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else None

async def submit_punishment_proof(assignment_id: int, proof_url: str) -> bool:
    """Submit proof of punishment completion."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Allow submission for both 'pending' and 'expired' punishments
        await db.execute("""
            UPDATE assigned_rewards_punishments 
            SET proof_url = ?, completion_status = 'submitted', submitted_at = CURRENT_TIMESTAMP
            WHERE id = ? AND type = 'punishment' AND completion_status IN ('pending', 'expired')
        """, (proof_url, assignment_id))
        await db.commit()
        return True

async def approve_punishment_completion(assignment_id: int, reviewer_id: int, approved: bool) -> Optional[int]:
    """Approve or reject punishment proof. Returns penalty if approved (to refund if late)."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Get assignment info
        async with db.execute("""
            SELECT submissive_id, point_penalty, completion_status 
            FROM assigned_rewards_punishments 
            WHERE id = ? AND type = 'punishment'
        """, (assignment_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[2] not in ('submitted', 'expired'):
                return None
            submissive_id, penalty, status = row
        
        new_status = 'approved' if approved else 'rejected'
        
        # Update assignment
        await db.execute("""
            UPDATE assigned_rewards_punishments 
            SET completion_status = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_status, reviewer_id, assignment_id))
        
        await db.commit()
        return penalty if approved and status == 'expired' else 0

async def get_pending_punishments(dominant_id: int) -> List[Dict[str, Any]]:
    """Get pending punishment proofs for review."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT ap.*, p.title, p.description, u.username as submissive_name
            FROM assigned_rewards_punishments ap
            JOIN punishments p ON ap.item_id = p.id
            JOIN users u ON ap.submissive_id = u.user_id
            WHERE ap.dominant_id = ? AND ap.type = 'punishment' 
            AND ap.completion_status IN ('submitted', 'expired')
            ORDER BY ap.submitted_at ASC
        """, (dominant_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def cancel_punishment(assignment_id: int, reviewer_id: int) -> Optional[Dict[str, Any]]:
    """Cancel a punishment and refund penalty points if already deducted. Returns dict with submissive_id and refunded penalty."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Get assignment info
        async with db.execute("""
            SELECT submissive_id, point_penalty, completion_status 
            FROM assigned_rewards_punishments 
            WHERE id = ? AND type = 'punishment'
        """, (assignment_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[2] in ('approved', 'rejected'):
                return None  # Already reviewed or doesn't exist
            submissive_id, penalty, status = row
        
        # Mark as approved (cancelled)
        await db.execute("""
            UPDATE assigned_rewards_punishments 
            SET completion_status = 'approved', reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (reviewer_id, assignment_id))
        
        await db.commit()
        
        # Return info for point refund - refund if it was expired (points already deducted)
        refund_amount = penalty if status == 'expired' else 0
        return {
            'submissive_id': submissive_id,
            'refund_penalty': refund_amount
        }

async def get_active_punishments(submissive_id: int) -> List[Dict[str, Any]]:
    """Get active punishments for a submissive."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT ap.*, p.title, p.description
            FROM assigned_rewards_punishments ap
            JOIN punishments p ON ap.item_id = p.id
            WHERE ap.submissive_id = ? AND ap.type = 'punishment' 
            AND ap.completion_status = 'pending'
            ORDER BY ap.deadline ASC
        """, (submissive_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_expired_punishments() -> List[Dict[str, Any]]:
    """Get punishments that passed deadline without proof."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM assigned_rewards_punishments
            WHERE type = 'punishment'
            AND completion_status = 'pending'
            AND deadline IS NOT NULL
            AND deadline < CURRENT_TIMESTAMP
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def expire_punishment(assignment_id: int, double_penalty: bool = True):
    """Mark punishment as expired and optionally double the penalty."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        if double_penalty:
            await db.execute("""
                UPDATE assigned_rewards_punishments 
                SET completion_status = 'expired', point_penalty = point_penalty * 2
                WHERE id = ?
            """, (assignment_id,))
        else:
            await db.execute("""
                UPDATE assigned_rewards_punishments 
                SET completion_status = 'expired'
                WHERE id = ?
            """, (assignment_id,))
        await db.commit()

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

# Task punishment linking
async def link_task_punishment(task_id: int, punishment_id: int, dominant_id: int) -> bool:
    """Link a punishment to a task (auto-assigns if task deadline missed)."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Verify dominant owns both task and punishment
        async with db.execute("SELECT id FROM tasks WHERE id = ? AND dominant_id = ?", (task_id, dominant_id)) as cursor:
            if not await cursor.fetchone():
                return False
        
        async with db.execute("SELECT id FROM punishments WHERE id = ? AND dominant_id = ?", (punishment_id, dominant_id)) as cursor:
            if not await cursor.fetchone():
                return False
        
        # Link punishment to task
        await db.execute("UPDATE tasks SET auto_punishment_id = ? WHERE id = ?", (punishment_id, task_id))
        await db.commit()
        return True

async def get_task_punishment(task_id: int) -> Optional[int]:
    """Get the linked punishment ID for a task."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        async with db.execute("SELECT auto_punishment_id FROM tasks WHERE id = ?", (task_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else None

# Point threshold triggers
async def create_point_threshold(dominant_id: int, threshold_points: int, punishment_id: int, submissive_id: int = None) -> int:
    """Create a point threshold trigger."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO point_thresholds (dominant_id, submissive_id, threshold_points, punishment_id)
            VALUES (?, ?, ?, ?)
        """, (dominant_id, submissive_id, threshold_points, punishment_id))
        await db.commit()
        return cursor.lastrowid

async def check_point_thresholds(submissive_id: int, current_points: int) -> List[Dict[str, Any]]:
    """Check if submissive triggered any point thresholds."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT pt.*, p.title, p.description
            FROM point_thresholds pt
            JOIN punishments p ON pt.punishment_id = p.id
            WHERE pt.active = 1
            AND (pt.submissive_id = ? OR pt.submissive_id IS NULL)
            AND pt.threshold_points > ?
            AND (pt.last_triggered_at IS NULL OR pt.last_triggered_at < datetime('now', '-1 day'))
        """, (submissive_id, current_points)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def mark_threshold_triggered(threshold_id: int):
    """Mark a threshold as triggered."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute(
            "UPDATE point_thresholds SET last_triggered_at = CURRENT_TIMESTAMP WHERE id = ?",
            (threshold_id,)
        )
        await db.commit()

async def get_point_thresholds(dominant_id: int) -> List[Dict[str, Any]]:
    """Get all point thresholds for a dominant."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT pt.*, p.title as punishment_title, u.username as submissive_name
            FROM point_thresholds pt
            JOIN punishments p ON pt.punishment_id = p.id
            LEFT JOIN users u ON pt.submissive_id = u.user_id
            WHERE pt.dominant_id = ? AND pt.active = 1
            ORDER BY pt.threshold_points DESC
        """, (dominant_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def delete_point_threshold(threshold_id: int, dominant_id: int) -> bool:
    """Delete a point threshold."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        async with db.execute("SELECT id FROM point_thresholds WHERE id = ? AND dominant_id = ?", (threshold_id, dominant_id)) as cursor:
            if not await cursor.fetchone():
                return False
        
        await db.execute("DELETE FROM point_thresholds WHERE id = ?", (threshold_id,))
        await db.commit()
        return True

# Random punishment assignment
async def get_random_punishment(dominant_id: int) -> Optional[Dict[str, Any]]:
    """Get a random punishment from available punishments."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM punishments 
            WHERE dominant_id = ? 
            ORDER BY RANDOM() 
            LIMIT 1
        """, (dominant_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

# Autocomplete helper functions
async def get_punishment_by_name(dominant_id: int, title: str) -> Optional[Dict[str, Any]]:
    """Get a punishment by its title."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM punishments WHERE dominant_id = ? AND title = ?",
            (dominant_id, title)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_reward_by_name(dominant_id: int, title: str) -> Optional[Dict[str, Any]]:
    """Get a reward by its title."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM rewards WHERE dominant_id = ? AND title = ?",
            (dominant_id, title)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_task_by_name(dominant_id: int, submissive_id: int, title: str) -> Optional[Dict[str, Any]]:
    """Get an active task by its title for a specific submissive."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tasks WHERE dominant_id = ? AND submissive_id = ? AND title = ? AND active = 1",
            (dominant_id, submissive_id, title)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_pending_task_completions_for_autocomplete(dominant_id: int) -> List[Dict[str, Any]]:
    """Get pending task completions with task info for autocomplete."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT tc.id, tc.task_id, t.title, u.username as submissive_name
            FROM task_completions tc
            JOIN tasks t ON tc.task_id = t.id
            JOIN users u ON tc.submissive_id = u.user_id
            WHERE t.dominant_id = ? AND tc.approval_status = 'pending'
            ORDER BY tc.submitted_at ASC
        """, (dominant_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_pending_punishment_assignments_for_autocomplete(dominant_id: int) -> List[Dict[str, Any]]:
    """Get pending/submitted punishment assignments with punishment info for autocomplete."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        print(f"[DB] Querying punishment assignments for dominant_id={dominant_id}")
        async with db.execute("""
            SELECT ap.id, ap.item_id, p.title, u.username as submissive_name, ap.completion_status
            FROM assigned_rewards_punishments ap
            JOIN punishments p ON ap.item_id = p.id
            JOIN users u ON ap.submissive_id = u.user_id
            WHERE ap.dominant_id = ? AND ap.type = 'punishment' 
            AND ap.completion_status IN ('submitted', 'expired')
            ORDER BY ap.submitted_at ASC
        """, (dominant_id,)) as cursor:
            rows = await cursor.fetchall()
            result = [dict(row) for row in rows]
            print(f"[DB] Query returned {len(result)} rows: {result}")
            return result

# Reminder operations
async def get_tasks_needing_reminders() -> List[Dict[str, Any]]:
    """Get active tasks with reminders that need to be sent."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT t.*, u.user_id as submissive_user_id
            FROM tasks t
            JOIN users u ON t.submissive_id = u.user_id
            WHERE t.active = 1 
            AND t.reminder_interval_hours IS NOT NULL
            AND t.deadline IS NOT NULL
            AND t.deadline > CURRENT_TIMESTAMP
            AND (
                t.last_reminder_sent IS NULL 
                OR datetime(t.last_reminder_sent, '+' || t.reminder_interval_hours || ' hours') <= CURRENT_TIMESTAMP
            )
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_punishments_needing_reminders() -> List[Dict[str, Any]]:
    """Get active punishment assignments with reminders that need to be sent."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT ap.*, p.title, p.description
            FROM assigned_rewards_punishments ap
            JOIN punishments p ON ap.item_id = p.id
            WHERE ap.type = 'punishment'
            AND ap.completion_status = 'pending'
            AND ap.reminder_interval_hours IS NOT NULL
            AND ap.deadline IS NOT NULL
            AND ap.deadline > CURRENT_TIMESTAMP
            AND (
                ap.last_reminder_sent IS NULL 
                OR datetime(ap.last_reminder_sent, '+' || ap.reminder_interval_hours || ' hours') <= CURRENT_TIMESTAMP
            )
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def update_task_reminder_sent(task_id: int):
    """Update the last reminder sent timestamp for a task."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute(
            "UPDATE tasks SET last_reminder_sent = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,)
        )
        await db.commit()

async def update_punishment_reminder_sent(assignment_id: int):
    """Update the last reminder sent timestamp for a punishment assignment."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute(
            "UPDATE assigned_rewards_punishments SET last_reminder_sent = CURRENT_TIMESTAMP WHERE id = ?",
            (assignment_id,)
        )
        await db.commit()
