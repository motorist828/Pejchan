"""
Timeout and Ban Management Module using SQLite
Handles user timeouts and bans.
"""

import threading
from datetime import datetime, timedelta, timezone
import sqlite3
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Database Configuration ---
DATABASE_DIR = 'instance'
DATABASE_PATH = os.path.join(DATABASE_DIR, 'imageboard.db') # Use the same DB file

def get_db_conn():
    """Establishes a connection to the SQLite database."""
    # Duplicated from database_module for simplicity here, consider a shared db utility
    try:
        os.makedirs(DATABASE_DIR, exist_ok=True)
        conn = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}", exc_info=True)
        raise

# --- Helper for executing queries (similar to database_module) ---
def execute_query(query, params=(), fetchone=False, commit=False):
    """Executes a given SQL query for moderation tables."""
    conn = None
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(query, params)
        if commit:
            conn.commit()
            return cursor.lastrowid
        if fetchone:
            return cursor.fetchone()
        else:
            return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Moderation DB query error: {e}\nQuery: {query}\nParams: {params}", exc_info=True)
        if conn and commit: conn.rollback()
        return None
    except Exception as e:
         logger.error(f"Unexpected error during moderation query: {e}", exc_info=True)
         if conn and commit: conn.rollback()
         return None
    finally:
        if conn:
            conn.close()

# --- Timeout Management ---
class TimeoutManager:
    def __init__(self):
        self.lock = threading.Lock() # Protect access if timers modify DB directly
        self.active_timers = {} # Store timers keyed by IP for cancellation
        self.cleanup_expired() # Clean up on startup

    def apply_timeout(self, user_ip, duration_seconds=35, reason="", moderator="System"):
        """Apply or update a timeout for a user."""
        with self.lock:
            now = datetime.now(timezone.utc)
            end_time_dt = now + timedelta(seconds=duration_seconds)
            end_time_iso = end_time_dt.isoformat()
            applied_at_iso = now.isoformat()

            # Use INSERT OR REPLACE for simplicity (requires UNIQUE constraint on user_ip)
            sql = """
                INSERT OR REPLACE INTO timeouts (user_ip, end_time, reason, moderator, applied_at)
                VALUES (?, ?, ?, ?, ?)
            """
            params = (user_ip, end_time_iso, reason, moderator, applied_at_iso)

            result = execute_query(sql, params, commit=True)

            if result is not None:
                logger.info(f"Timeout applied/updated for IP {user_ip} until {end_time_iso}. Reason: {reason}")
                # Restart timer if needed
                self._setup_timer(user_ip, duration_seconds)
                return True
            else:
                logger.error(f"Failed to apply timeout for IP {user_ip}.")
                return False

    def _setup_timer(self, user_ip, duration):
        """Setup or reset a timer to automatically remove timeout."""
        # Cancel existing timer for this IP if it exists
        if user_ip in self.active_timers:
            self.active_timers[user_ip].cancel()

        # Create and start a new timer
        # Note: The timer calls remove_timeout_by_ip, which needs to be thread-safe
        timer = threading.Timer(duration, self.remove_timeout_by_ip, args=[user_ip])
        timer.daemon = True # Allow program to exit even if timers are running
        timer.start()
        self.active_timers[user_ip] = timer

    def remove_timeout_by_ip(self, user_ip):
        """Remove a timeout by user IP."""
        with self.lock:
            logger.info(f"Attempting to remove timeout for IP: {user_ip}")
            sql = "DELETE FROM timeouts WHERE user_ip = ?"
            execute_query(sql, (user_ip,), commit=True)
            # Clean up timer reference
            if user_ip in self.active_timers:
                del self.active_timers[user_ip]

    def check_timeout(self, user_ip):
        """Check if a user is currently timed out."""
        sql = "SELECT * FROM timeouts WHERE user_ip = ?"
        timeout = execute_query(sql, (user_ip,), fetchone=True)

        if not timeout:
            return {'is_timeout': False}

        try:
            end_time = datetime.fromisoformat(timeout['end_time'].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)

            if now < end_time:
                return {
                    'is_timeout': True,
                    'end_time': end_time, # Return datetime object
                    'reason': timeout.get('reason', ''),
                    'moderator': timeout.get('moderator', 'System')
                    # 'timeout_id' is less relevant now we use IP as key
                }
            else:
                # Timeout expired, remove it
                logger.info(f"Expired timeout found for IP {user_ip}. Removing.")
                self.remove_timeout_by_ip(user_ip)
                return {'is_timeout': False}
        except (ValueError, TypeError) as e:
             logger.error(f"Error parsing timeout end_time '{timeout['end_time']}' for IP {user_ip}: {e}")
             # Treat as invalid/expired? Or raise? For safety, treat as not timed out.
             self.remove_timeout_by_ip(user_ip) # Remove potentially corrupt entry
             return {'is_timeout': False}


    def cleanup_expired(self):
        """Remove all expired timeouts from the database."""
        with self.lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            sql = "DELETE FROM timeouts WHERE end_time <= ?"
            logger.info("Cleaning up expired timeouts...")
            execute_query(sql, (now_iso,), commit=True)
            logger.info("Expired timeouts cleanup complete.")

# --- Ban Management ---
class BanManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_timers = {} # Store timers keyed by IP for temporary bans
        self.cleanup_expired() # Clean up on startup

    def ban_user(self, user_ip, duration_seconds=None, reason="", moderator="System"):
        """Ban or update a ban for a user."""
        with self.lock:
            now = datetime.now(timezone.utc)
            applied_at_iso = now.isoformat()
            is_permanent = duration_seconds is None

            end_time_iso = None
            if not is_permanent:
                end_time_dt = now + timedelta(seconds=duration_seconds)
                end_time_iso = end_time_dt.isoformat()

            # Use INSERT OR REPLACE for simplicity
            sql = """
                INSERT OR REPLACE INTO bans (user_ip, end_time, reason, moderator, applied_at, is_permanent)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            params = (user_ip, end_time_iso, reason, moderator, applied_at_iso, 1 if is_permanent else 0)

            result = execute_query(sql, params, commit=True)

            if result is not None:
                ban_type = "Permanent" if is_permanent else f"Temporary until {end_time_iso}"
                logger.info(f"{ban_type} ban applied/updated for IP {user_ip}. Reason: {reason}")
                if not is_permanent:
                    self._setup_timer(user_ip, duration_seconds)
                else:
                    # Cancel any existing timer if the ban became permanent
                    if user_ip in self.active_timers:
                         self.active_timers[user_ip].cancel()
                         del self.active_timers[user_ip]
                return True
            else:
                logger.error(f"Failed to apply ban for IP {user_ip}.")
                return False

    def _setup_timer(self, user_ip, duration):
        """Setup or reset timer for temporary bans."""
        if user_ip in self.active_timers:
            self.active_timers[user_ip].cancel()

        timer = threading.Timer(duration, self.unban_user, args=[user_ip])
        timer.daemon = True
        timer.start()
        self.active_timers[user_ip] = timer

    def unban_user(self, user_ip):
        """Remove a ban by user IP."""
        with self.lock:
            logger.info(f"Attempting to unban IP: {user_ip}")
            sql = "DELETE FROM bans WHERE user_ip = ?"
            execute_query(sql, (user_ip,), commit=True)
            # Clean up timer reference
            if user_ip in self.active_timers:
                 self.active_timers[user_ip].cancel() # Ensure timer is stopped
                 del self.active_timers[user_ip]
            logger.info(f"Ban removed for IP: {user_ip}")
            return True # Assume success if no error

    def is_banned(self, user_ip):
        """Check if a user is currently banned."""
        sql = "SELECT * FROM bans WHERE user_ip = ?"
        ban = execute_query(sql, (user_ip,), fetchone=True)

        if not ban:
            return {'is_banned': False}

        if ban['is_permanent'] == 1:
             applied_at = datetime.fromisoformat(ban['applied_at'].replace('Z', '+00:00'))
             return {
                'is_banned': True,
                'is_permanent': True,
                'reason': ban.get('reason', ''),
                'moderator': ban.get('moderator', 'System'),
                'applied_at': applied_at # Return datetime object
             }
        else:
            try:
                end_time = datetime.fromisoformat(ban['end_time'].replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)

                if now < end_time:
                    applied_at = datetime.fromisoformat(ban['applied_at'].replace('Z', '+00:00'))
                    return {
                        'is_banned': True,
                        'is_permanent': False,
                        'end_time': end_time, # Return datetime object
                        'reason': ban.get('reason', ''),
                        'moderator': ban.get('moderator', 'System'),
                        'applied_at': applied_at # Return datetime object
                    }
                else:
                    # Ban expired, remove it
                    logger.info(f"Expired temporary ban found for IP {user_ip}. Removing.")
                    self.unban_user(user_ip)
                    return {'is_banned': False}
            except (ValueError, TypeError) as e:
                 logger.error(f"Error parsing ban end_time '{ban['end_time']}' for IP {user_ip}: {e}")
                 # Treat as invalid/expired for safety
                 self.unban_user(user_ip)
                 return {'is_banned': False}


    def cleanup_expired(self):
        """Remove all expired temporary bans."""
        with self.lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            # Delete non-permanent bans where end_time is past
            sql = "DELETE FROM bans WHERE is_permanent = 0 AND end_time <= ?"
            logger.info("Cleaning up expired temporary bans...")
            execute_query(sql, (now_iso,), commit=True)
            logger.info("Expired temporary bans cleanup complete.")


if __name__ == '__main__':
    logger.info("Moderation module loaded. Running example checks.")
    # Add any specific tests for moderation here if needed
    # Example: test timeout
    # tm = TimeoutManager()
    # tm.apply_timeout('127.0.0.1', 5, 'Testing timeout')
    # print(tm.check_timeout('127.0.0.1'))
    # import time
    # time.sleep(6)
    # print(tm.check_timeout('127.0.0.1'))
    logger.info("This module should be imported.")