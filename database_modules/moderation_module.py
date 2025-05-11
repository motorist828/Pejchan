# --- START OF FILE moderation_module.py ---

"""
Timeout and Ban Management Module using SQLite
Handles user timeouts and bans.
Relies on database_module for DB connection and query execution.
"""

import threading
from datetime import datetime, timedelta, timezone
# sqlite3 и os теперь не нужны здесь напрямую, если get_db_conn и execute_query импортируются
import logging

# --- Импортируем необходимые функции из database_module ---
# Предполагается, что moderation_module.py и database_module.py находятся
# внутри одного пакета 'database_modules'.
# Точка перед database_module указывает на относительный импорт внутри текущего пакета.
from .database_module import (
    get_db_conn,
    execute_query,
    parse_datetime,             # Импортируем напрямую
    format_datetime_for_display # Импортируем напрямую
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Timeout Management ---
class TimeoutManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_timers = {}
        self.cleanup_expired()

    def apply_timeout(self, user_ip, duration_seconds=35, reason="", moderator="System"):
        with self.lock:
            now = datetime.now(timezone.utc)
            end_time_dt = now + timedelta(seconds=duration_seconds)
            end_time_iso = end_time_dt.isoformat()
            applied_at_iso = now.isoformat()

            sql = """
                INSERT OR REPLACE INTO timeouts (user_ip, end_time, reason, moderator, applied_at)
                VALUES (?, ?, ?, ?, ?)
            """
            params = (user_ip, end_time_iso, reason, moderator, applied_at_iso)

            # Используем импортированную execute_query
            # fetchall=False указывает, что нам не нужен список результатов для INSERT/REPLACE
            result = execute_query(sql, params, commit=True, fetchall=False)

            if result is not None: # lastrowid или None при ошибке
                logger.info(f"Timeout applied/updated for IP {user_ip} until {end_time_iso}. Reason: {reason}")
                self._setup_timer(user_ip, duration_seconds)
                return True
            else:
                logger.error(f"Failed to apply timeout for IP {user_ip}.")
                return False

    def _setup_timer(self, user_ip, duration):
        if user_ip in self.active_timers:
            self.active_timers[user_ip].cancel()
        timer = threading.Timer(duration, self.remove_timeout_by_ip, args=[user_ip])
        timer.daemon = True
        timer.start()
        self.active_timers[user_ip] = timer

    def remove_timeout_by_ip(self, user_ip):
        with self.lock:
            logger.info(f"Attempting to remove timeout for IP: {user_ip}")
            sql = "DELETE FROM timeouts WHERE user_ip = ?"
            execute_query(sql, (user_ip,), commit=True, fetchall=False)
            if user_ip in self.active_timers:
                try: self.active_timers[user_ip].cancel()
                except Exception: pass # Игнорируем ошибки при отмене, если таймер уже завершился
                del self.active_timers[user_ip]

    def check_timeout(self, user_ip):
        sql = "SELECT * FROM timeouts WHERE user_ip = ?"
        timeout_row = execute_query(sql, (user_ip,), fetchone=True)

        if not timeout_row:
            return {'is_timeout': False}
        
        timeout = dict(timeout_row) # Конвертируем sqlite3.Row в dict для удобства
        try:
            end_time_str = timeout.get('end_time')
            end_time = parse_datetime(end_time_str) # Используем импортированную функцию
            now = datetime.now(timezone.utc)

            if end_time and now < end_time:
                return {
                    'is_timeout': True,
                    'end_time': end_time,
                    'reason': timeout.get('reason', ''),
                    'moderator': timeout.get('moderator', 'System')
                }
            else:
                if end_time is None and end_time_str:
                     logger.error(f"Could not parse end_time '{end_time_str}' for timeout IP {user_ip}.")
                logger.info(f"Expired or unparseable timeout found for IP {user_ip}. Removing.")
                self.remove_timeout_by_ip(user_ip)
                return {'is_timeout': False}
        except Exception as e:
             logger.error(f"Error processing timeout for IP {user_ip}: {e}", exc_info=True)
             self.remove_timeout_by_ip(user_ip) # Удаляем при любой ошибке обработки
             return {'is_timeout': False}


    def cleanup_expired(self):
        with self.lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            sql = "DELETE FROM timeouts WHERE end_time <= ?"
            logger.info("Cleaning up expired timeouts...")
            execute_query(sql, (now_iso,), commit=True, fetchall=False)
            logger.info("Expired timeouts cleanup complete.")

# --- Ban Management ---
class BanManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_timers = {}
        self.cleanup_expired()

    def ban_user(self, user_ip, duration_seconds=None, reason="", moderator="System"):
        with self.lock:
            now = datetime.now(timezone.utc)
            applied_at_iso = now.isoformat()
            is_permanent = duration_seconds is None
            end_time_iso = None
            if not is_permanent and isinstance(duration_seconds, (int, float)) and duration_seconds > 0:
                end_time_dt = now + timedelta(seconds=duration_seconds)
                end_time_iso = end_time_dt.isoformat()
            elif not is_permanent: # Если duration_seconds некорректный (0 или не число), считаем перманентным
                logger.warning(f"Invalid duration_seconds '{duration_seconds}' for temporary ban on IP {user_ip}. Setting to permanent.")
                is_permanent = True


            sql = """
                INSERT OR REPLACE INTO bans (user_ip, end_time, reason, moderator, applied_at, is_permanent)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            params = (user_ip, end_time_iso, reason, moderator, applied_at_iso, 1 if is_permanent else 0)
            result = execute_query(sql, params, commit=True, fetchall=False)

            if result is not None:
                ban_type = "Permanent" if is_permanent else f"Temporary until {end_time_iso}"
                logger.info(f"{ban_type} ban applied/updated for IP {user_ip}. Reason: {reason}")
                # Управляем таймером
                if not is_permanent and duration_seconds and duration_seconds > 0:
                    self._setup_timer(user_ip, duration_seconds)
                elif user_ip in self.active_timers: # Если бан стал перманентным или длительность 0
                    try: self.active_timers[user_ip].cancel()
                    except Exception: pass
                    del self.active_timers[user_ip]
                return True
            else:
                logger.error(f"Failed to apply ban for IP {user_ip}.")
                return False

    def _setup_timer(self, user_ip, duration):
        if user_ip in self.active_timers:
            self.active_timers[user_ip].cancel()
        timer = threading.Timer(duration, self.unban_user, args=[user_ip])
        timer.daemon = True
        timer.start()
        self.active_timers[user_ip] = timer

    def unban_user(self, user_ip):
        with self.lock:
            logger.info(f"Attempting to unban IP: {user_ip}")
            sql = "DELETE FROM bans WHERE user_ip = ?"
            result = execute_query(sql, (user_ip,), commit=True, fetchall=False)

            # result будет lastrowid (не очень полезно для DELETE) или None при ошибке
            # Проверяем, что не было ошибки (result is not None)
            if result is not None:
                if user_ip in self.active_timers:
                    try: self.active_timers[user_ip].cancel()
                    except Exception as e_timer: logger.warning(f"Could not cancel timer for unbanned IP {user_ip}: {e_timer}")
                    del self.active_timers[user_ip]
                logger.info(f"Ban for IP {user_ip} lifted.")
                return True
            else:
                logger.error(f"Error lifting ban for IP {user_ip} (DB query failed).")
                return False


    def get_active_bans(self):
        active_bans_list = []
        now_utc = datetime.now(timezone.utc)
        all_bans_db = execute_query("SELECT * FROM bans", fetchall=True)

        if not all_bans_db:
            return []

        for ban_row in all_bans_db:
            ban = dict(ban_row) # Конвертируем sqlite3.Row в словарь
            keep_ban = False
            ban_info_for_template = {
                'user_ip': ban['user_ip'],
                'reason': ban.get('reason', 'N/A'),
                'moderator': ban.get('moderator', 'System'),
                'applied_at_raw': ban['applied_at'],
                'is_permanent': bool(ban.get('is_permanent', 0))
            }

            applied_at_dt = parse_datetime(ban['applied_at']) # Используем импортированную функцию
            ban_info_for_template['applied_at_display'] = format_datetime_for_display(applied_at_dt) if applied_at_dt else 'N/A'

            if ban_info_for_template['is_permanent']:
                ban_info_for_template['end_time_display'] = "Permanent"
                keep_ban = True
            else:
                end_time_str = ban.get('end_time')
                if end_time_str:
                    end_time_dt = parse_datetime(end_time_str) # Используем импортированную функцию
                    if end_time_dt and now_utc < end_time_dt:
                        ban_info_for_template['end_time_display'] = format_datetime_for_display(end_time_dt)
                        keep_ban = True
                    elif end_time_dt and now_utc >= end_time_dt:
                        logger.info(f"Expired temporary ban for IP {ban['user_ip']} found in get_active_bans. Removing.")
                        self.unban_user(ban['user_ip']) # Удалит бан и связанный таймер
                    elif not end_time_dt : # Ошибка парсинга end_time_str
                        logger.error(f"Could not parse end_time '{end_time_str}' for ban IP {ban['user_ip']}. Removing ban.")
                        self.unban_user(ban['user_ip']) # Удаляем некорректный бан
                else: # Временный бан без end_time - некорректно
                    logger.warning(f"Temporary ban for IP {ban['user_ip']} has no end_time. Removing ban.")
                    self.unban_user(ban['user_ip']) # Удаляем некорректный бан
            
            if keep_ban:
                active_bans_list.append(ban_info_for_template)

        active_bans_list.sort(key=lambda x: x['applied_at_raw'], reverse=True)
        return active_bans_list

    def is_banned(self, user_ip):
        sql = "SELECT * FROM bans WHERE user_ip = ?"
        ban_row = execute_query(sql, (user_ip,), fetchone=True)

        if not ban_row:
            return {'is_banned': False}
        
        ban = dict(ban_row) # Конвертируем в dict

        if ban.get('is_permanent') == 1:
             applied_at_dt = parse_datetime(ban['applied_at']) # Используем импортированную функцию
             return {
                'is_banned': True,
                'is_permanent': True,
                'reason': ban.get('reason', ''),
                'moderator': ban.get('moderator', 'System'),
                'applied_at': applied_at_dt
             }
        else:
            end_time_str = ban.get('end_time')
            if end_time_str:
                end_time_dt = parse_datetime(end_time_str) # Используем импортированную функцию
                now = datetime.now(timezone.utc)

                if end_time_dt and now < end_time_dt:
                    applied_at_dt = parse_datetime(ban['applied_at'])
                    return {
                        'is_banned': True,
                        'is_permanent': False,
                        'end_time': end_time_dt,
                        'reason': ban.get('reason', ''),
                        'moderator': ban.get('moderator', 'System'),
                        'applied_at': applied_at_dt
                    }
                elif end_time_dt and now >= end_time_dt: # Бан истек
                    logger.info(f"Expired temporary ban for IP {user_ip} checked by is_banned. Removing.")
                    self.unban_user(user_ip)
                    return {'is_banned': False}
                elif not end_time_dt : # Ошибка парсинга
                     logger.error(f"Could not parse end_time '{end_time_str}' for is_banned check IP {user_ip}. Removing ban.")
                     self.unban_user(user_ip)
                     return {'is_banned': False}
            else: # Временный бан без end_time
                 logger.warning(f"Temporary ban for IP {user_ip} has no end_time in is_banned. Removing ban.")
                 self.unban_user(user_ip)
                 return {'is_banned': False}
        
        # На случай, если ни одно из условий выше не выполнилось (не должно происходить)
        return {'is_banned': False}


    def cleanup_expired(self):
        with self.lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            # Удаляем только временные баны (is_permanent = 0), у которых есть end_time
            sql = "DELETE FROM bans WHERE is_permanent = 0 AND end_time IS NOT NULL AND end_time <= ?"
            logger.info("Cleaning up expired temporary bans...")
            execute_query(sql, (now_iso,), commit=True, fetchall=False)
            logger.info("Expired temporary bans cleanup complete.")


if __name__ == '__main__':
    logger.info("Moderation module loaded (run directly). Example checks can be added here.")
    logger.info("This module should typically be imported by other parts of the application.")

# --- END OF FILE moderation_module.py ---