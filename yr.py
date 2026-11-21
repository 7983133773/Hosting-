# -*- coding: utf-8 -*-
import subprocess
import sys
import os

# ✅ Auto-install missing modules
def auto_install(package):
    try:
        __import__(package)
    except ModuleNotFoundError:
        print(f"📦 Installing missing package: {package} ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"✅ Installed: {package}")

# Auto-install required modules
for mod in ["telebot", "psutil", "requests", "flask"]:
    auto_install(mod)

# --- After auto-install, import all modules safely ---
import telebot
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import json
import logging
import signal
import threading
import re
import atexit
import requests
from flask import Flask, request, jsonify
from threading import Thread

# ============================================================
# 🆕 FLASK APP — Webhook + /health for Render
# ============================================================
app = Flask('')

# 🆕 Webhook config
USE_WEBHOOK = os.environ.get("USE_WEBHOOK", "false").lower() == "true"
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").rstrip('/')
PORT = int(os.environ.get("PORT", os.environ.get("BOT_PORT", 6000)))

@app.route('/')
def home():
    return "AYUSH HOSTER BOT"

@app.route('/health')
def health():
    """🆕 Render health check endpoint."""
    try:
        running = 0
        for k in bot_scripts:
            p = k.split('|')
            if len(p) == 3 and is_bot_running(int(p[0]), p[2], p[1]):
                running += 1
    except Exception:
        running = 0
    return jsonify({
        "status": "ok",
        "bot": "AYUSH HOSTER BOT",
        "time": str(datetime.now()),
        "running_scripts": running,
        "total_users": len(active_users),
        "total_files": sum(len(f) for f in user_files.values()),
        "locked": bot_locked,
        "auto_restart": auto_restart_enabled,
        "webhook_mode": USE_WEBHOOK,
        "version": "2.0"
    }), 200

def run_flask():
    app.run(host='0.0.0.0', port=PORT)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print(f"🌐 Flask Keep-Alive server started on port {PORT}")

# ============================================================
# --- Configuration ---
# ============================================================
TOKEN = '9040798388:AAFRGz3Du9gyFajJCIwqilGh3j3J_xJB03k'
OWNER_ID = 7758917200
ADMIN_ID = 7758917200
YOUR_USERNAME = 'GOD_AYUSH'
UPDATE_CHANNEL = 'https://t.me/Ayush_Hackz'

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')  # 🆕

FREE_USER_LIMIT = 1
SUBSCRIBED_USER_LIMIT = 50
ADMIN_LIMIT = 15
OWNER_LIMIT = float('inf')

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)  # 🆕

bot = telebot.TeleBot(TOKEN)

# ============================================================
# --- Data structures ---
# ============================================================
bot_scripts = {}
user_subscriptions = {}
user_custom_limits = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False
users_awaiting_upload = set()
users_pending_folder = {}

# 🆕 Ban system
banned_users = {}

# 🆕 Auto Restart system
auto_restart_enabled = True
auto_restart_tracker = {}
MAX_AUTO_RESTARTS = 5
RESTART_WINDOW = 300  # 5 minutes

# ============================================================
# --- Logging Setup ---
# ============================================================
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# --- Command Button Layouts ---
# ============================================================
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["📞 Contact Owner"]
]
ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["💳 Subscriptions", "📢 Broadcast"],
    ["🔒 Lock Bot", "🟢 Running All Code"],
    ["🖥️ Hosting Dashboard", "📈 Resource Monitor"],   # 🆕
    ["💾 Backup All", "♻️ Auto Restart: ON"],           # 🆕
    ["👑 Admin Panel", "📞 Contact Owner"]
]

# ============================================================
# --- Database Setup ---
# ============================================================
def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT, file_limit INTEGER DEFAULT NULL)''')
        try:
            c.execute('ALTER TABLE subscriptions ADD COLUMN file_limit INTEGER DEFAULT NULL')
            conn.commit()
        except sqlite3.OperationalError:
            pass
        c.execute('''CREATE TABLE IF NOT EXISTS user_custom_limits
                     (user_id INTEGER PRIMARY KEY, file_limit INTEGER NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')
        # 🆕 banned_users table
        c.execute('''CREATE TABLE IF NOT EXISTS banned_users
                     (user_id INTEGER PRIMARY KEY, reason TEXT, name TEXT, username TEXT)''')
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)

def load_data():
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT user_id, expiry, file_limit FROM subscriptions')
        for row in c.fetchall():
            user_id, expiry, file_limit = row[0], row[1], row[2] if len(row) > 2 else None
            try:
                user_subscriptions[user_id] = {
                    'expiry': datetime.fromisoformat(expiry),
                    'file_limit': int(file_limit) if file_limit is not None else None
                }
            except ValueError:
                logger.warning(f"⚠️ Invalid expiry for user {user_id}: {expiry}")
        try:
            c.execute('SELECT user_id, file_limit FROM user_custom_limits')
            for user_id, file_limit in c.fetchall():
                user_custom_limits[user_id] = int(file_limit)
        except Exception:
            pass
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))
        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())
        # 🆕 Load banned users
        try:
            c.execute('SELECT user_id, reason, name, username FROM banned_users')
            for uid, reason, name, username in c.fetchall():
                banned_users[uid] = {'reason': reason, 'name': name, 'username': username}
        except Exception:
            pass
        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users, {len(user_subscriptions)} subs, {len(admin_ids)} admins, {len(banned_users)} banned.")
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)

init_db()
load_data()

# ============================================================
# --- Helper Functions ---
# ============================================================
def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def _get_user_folder_names(user_id):
    base = get_user_folder(user_id)
    try:
        return sorted(e.name for e in os.scandir(base) if e.is_dir())
    except Exception:
        return []

def _get_files_in_folder(user_id, folder_name):
    base = get_user_folder(user_id)
    folder_path = os.path.join(base, folder_name)
    if not os.path.isdir(folder_path):
        return []
    registered = {fn for fn, ft in user_files.get(user_id, [])}
    results = []
    try:
        for entry in sorted(os.scandir(folder_path), key=lambda e: e.name):
            if entry.is_file() and entry.name in registered:
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in ('.py', '.js'):
                    results.append((entry.name, ext.lstrip('.')))
    except Exception:
        pass
    return results

def _extract_folder_name(user_id, user_folder):
    base = get_user_folder(user_id)
    if os.path.normpath(user_folder) == os.path.normpath(base):
        return '__root__'
    rel = os.path.relpath(user_folder, base)
    return rel.split(os.sep)[0]

def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        custom = user_subscriptions[user_id].get('file_limit')
        return int(custom) if custom is not None else SUBSCRIBED_USER_LIMIT
    if user_id in user_custom_limits:
        return user_custom_limits[user_id]
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_bot_running(script_owner_id, file_name, folder_name=None):
    if folder_name is not None:
        script_key = f"{script_owner_id}|{folder_name}|{file_name}"
    else:
        script_key = None
        for k in list(bot_scripts.keys()):
            parts = k.split('|')
            if len(parts) == 3 and parts[0] == str(script_owner_id) and parts[2] == file_name:
                script_key = k
                break
        if script_key is None:
            return False
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not is_running:
                logger.warning(f"Process {script_info['process'].pid} for {script_key} found but not running. Cleaning up.")
                if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                    try: script_info['log_file'].close()
                    except Exception as log_e: logger.error(f"Error closing log file: {log_e}")
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            logger.warning(f"Process for {script_key} not found. Cleaning up.")
            if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                try: script_info['log_file'].close()
                except Exception as log_e: logger.error(f"Error closing log file: {log_e}")
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            return False
        except Exception as e:
            logger.error(f"Error checking process status for {script_key}: {e}", exc_info=True)
            return False
    return False


def kill_process_tree(process_info):
    pid = None
    log_file_closed = False
    script_key = process_info.get('script_key', 'N/A')
    try:
        if 'log_file' in process_info and hasattr(process_info['log_file'], 'close') and not process_info['log_file'].closed:
            try:
                process_info['log_file'].close()
                log_file_closed = True
                logger.info(f"Closed log file for {script_key}")
            except Exception as log_e:
                logger.error(f"Error closing log file for {script_key}: {log_e}")
        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
            pid = process.pid
            if pid:
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    logger.info(f"Killing tree for {script_key} (PID: {pid}, children: {[c.pid for c in children]})")
                    for child in children:
                        try:
                            child.terminate()
                        except psutil.NoSuchProcess:
                            pass
                        except Exception as e:
                            try: child.kill()
                            except Exception as e2: logger.error(f"Failed kill child {child.pid}: {e2}")
                    gone, alive = psutil.wait_procs(children, timeout=1)
                    for p in alive:
                        try: p.kill()
                        except Exception as e: logger.error(f"Failed kill child {p.pid}: {e}")
                    try:
                        parent.terminate()
                        try: parent.wait(timeout=1)
                        except psutil.TimeoutExpired:
                            parent.kill()
                    except psutil.NoSuchProcess:
                        pass
                    except Exception as e:
                        try: parent.kill()
                        except Exception as e2: logger.error(f"Failed kill parent {pid}: {e2}")
                except psutil.NoSuchProcess:
                    logger.warning(f"Process {pid} not found during kill.")
            else:
                logger.error(f"Process PID None for {script_key}.")
        elif log_file_closed:
            logger.warning(f"Process missing for {script_key}, but log closed.")
        else:
            logger.error(f"Process missing for {script_key}.")
    except Exception as e:
        logger.error(f"❌ Unexpected kill error PID {pid or 'N/A'} ({script_key}): {e}", exc_info=True)

# ============================================================
# 🆕 AUTO-RESTART MONITOR (background thread)
# ============================================================
def should_auto_restart(script_key):
    if not auto_restart_enabled:
        return False
    now = datetime.now()
    tracker = auto_restart_tracker.get(script_key)
    if not tracker:
        auto_restart_tracker[script_key] = {'count': 1, 'first': now, 'last': now}
        return True
    if (now - tracker['first']).total_seconds() > RESTART_WINDOW:
        auto_restart_tracker[script_key] = {'count': 1, 'first': now, 'last': now}
        return True
    if tracker['count'] >= MAX_AUTO_RESTARTS:
        logger.warning(f"🚫 {script_key}: Auto-restart limit reached.")
        return False
    tracker['count'] += 1
    tracker['last'] = now
    return True

def monitor_crashed_scripts():
    """🆕 Detect crashed scripts and auto-restart with limits."""
    while True:
        try:
            time.sleep(15)
            if not auto_restart_enabled:
                continue
            for script_key in list(bot_scripts.keys()):
                info = bot_scripts.get(script_key)
                if not info:
                    continue
                proc = info.get('process')
                if proc is None:
                    continue
                if proc.poll() is not None:
                    rc = proc.returncode
                    logger.warning(f"💥 Crashed: {script_key} (RC={rc})")
                    parts = script_key.split('|')
                    if len(parts) != 3:
                        continue
                    owner_id = int(parts[0])
                    folder = parts[1]
                    fname = parts[2]
                    if 'log_file' in info and hasattr(info['log_file'], 'close') and not info['log_file'].closed:
                        try: info['log_file'].close()
                        except: pass
                    if script_key in bot_scripts:
                        del bot_scripts[script_key]
                    if should_auto_restart(script_key):
                        base = get_user_folder(owner_id)
                        uf = os.path.join(base, folder) if folder != '__root__' else base
                        fp = os.path.join(uf, fname)
                        if os.path.exists(fp):
                            ftype = os.path.splitext(fname)[1].lower()
                            try:
                                bot.send_message(owner_id, f"♻️ `{fname}` crashed (RC={rc}). Auto-restarting...\nFolder: `{folder}`", parse_mode='Markdown')
                            except: pass
                            time.sleep(2)
                            dummy_msg = type('DummyMsg', (), {
                                'chat': type('Chat', (), {'id': owner_id})(),
                                'from_user': type('User', (), {'id': owner_id})()
                            })()
                            if ftype == '.py':
                                threading.Thread(target=run_script, args=(fp, owner_id, uf, fname, dummy_msg)).start()
                            elif ftype == '.js':
                                threading.Thread(target=run_js_script, args=(fp, owner_id, uf, fname, dummy_msg)).start()
                    else:
                        try:
                            bot.send_message(owner_id, f"🚫 `{fname}` crashed too many times. Auto-restart disabled for 5 min.", parse_mode='Markdown')
                        except: pass
        except Exception as e:
            logger.error(f"Monitor thread error: {e}", exc_info=True)

# ============================================================
# --- Automatic Package Installation ---
# ============================================================
def attempt_install_pip(module_name, message):
    package_name = TELEGRAM_MODULES.get(module_name.lower(), module_name)
    if package_name is None:
        logger.info(f"Module '{module_name}' is core. Skipping.")
        return False
    try:
        bot.reply_to(message, f"🐍 Module `{module_name}` not found. Installing `{package_name}`...", parse_mode='Markdown')
        install_methods = [
            [sys.executable, '-m', 'pip', 'install', package_name],
            [sys.executable, '-m', 'pip', 'install', '--user', package_name],
            [sys.executable, '-m', 'pip', 'install', '--break-system-packages', package_name],
        ]
        last_error = ""
        for command in install_methods:
            logger.info(f"Trying pip: {' '.join(command)}")
            result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore')
            if result.returncode == 0:
                logger.info(f"Installed {package_name}")
                bot.reply_to(message, f"✅ `{package_name}` installed.", parse_mode='Markdown')
                return True
            last_error = result.stderr or result.stdout
            logger.warning(f"Failed: {last_error[:200]}")
        error_msg = f"❌ Failed to install `{package_name}` (all methods).\nLog:\n```\n{last_error[:800]}\n```"
        if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n..."
        bot.reply_to(message, error_msg, parse_mode='Markdown')
        return False
    except Exception as e:
        error_msg = f"❌ Error installing `{package_name}`: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message, error_msg)
        return False

def attempt_install_npm(module_name, user_folder, message):
    try:
        bot.reply_to(message, f"🟠 Node `{module_name}` installing locally...", parse_mode='Markdown')
        command = ['npm', 'install', module_name]
        logger.info(f"npm install: {' '.join(command)} in {user_folder}")
        result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=user_folder, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            bot.reply_to(message, f"✅ Node `{module_name}` installed.", parse_mode='Markdown')
            return True
        error_msg = f"❌ Failed npm `{module_name}`.\nLog:\n```\n{result.stderr or result.stdout}\n```"
        logger.error(error_msg)
        if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n..."
        bot.reply_to(message, error_msg, parse_mode='Markdown')
        return False
    except FileNotFoundError:
        bot.reply_to(message, "❌ npm not found. Install Node.js.")
        return False
    except Exception as e:
        error_msg = f"❌ npm error `{module_name}`: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message, error_msg)
        return False

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    """Run Python script (original logic preserved)."""
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run '{file_name}' after {max_attempts} attempts.")
        return

    folder_name = _extract_folder_name(script_owner_id, user_folder)
    script_key = f"{script_owner_id}|{folder_name}|{file_name}"
    logger.info(f"Attempt {attempt}: {script_path} (Key: {script_key})")
    try:
        if not os.path.exists(script_path):
             bot.reply_to(message_obj_for_reply, f"❌ Script not found: `{script_path}`!")
             logger.error(f"Script missing: {script_path} for {script_owner_id}")
             if script_owner_id in user_files:
                 user_files[script_owner_id] = [f for f in user_files.get(script_owner_id, []) if f[0] != file_name]
             remove_user_file_db(script_owner_id, file_name)
             return

        if attempt == 1:
            check_command = [sys.executable, script_path]
            logger.info(f"Pre-check: {' '.join(check_command)}")
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode
                logger.info(f"Pre-check RC: {return_code}. Stderr: {stderr[:200]}...")
                if return_code != 0 and stderr:
                    match_py = re.search(r"ModuleNotFoundError: No module named '(.+?)'", stderr)
                    if match_py:
                        module_name = match_py.group(1).strip().strip("'\"")
                        logger.info(f"Missing Python module: {module_name}")
                        if attempt_install_pip(module_name, message_obj_for_reply):
                            bot.reply_to(message_obj_for_reply, f"🔄 Install OK. Retrying '{file_name}'...")
                            time.sleep(2)
                            threading.Thread(target=run_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                            return
                        else:
                            bot.reply_to(message_obj_for_reply, f"❌ Install failed. Cannot run '{file_name}'.")
                            return
                    else:
                        script_had_output = bool((stdout and stdout.strip()) or re.search(r'\b(INFO|WARNING|DEBUG|ERROR)\b', stderr or ''))
                        if script_had_output:
                            logger.warning(f"Pre-check: {script_key} crashed after running. Proceeding to long-run.")
                            bot.reply_to(message_obj_for_reply, f"⚠️ Script crash hua pre-check mein, lekin long-run mein try...", parse_mode='Markdown')
                        else:
                            logger.warning(f"Pre-check: {script_key} failed with no output. Proceeding anyway.")
            except subprocess.TimeoutExpired:
                logger.info("Pre-check timed out. Proceeding to long-run.")
                if check_proc and check_proc.poll() is None:
                    check_proc.kill(); check_proc.communicate()
            except FileNotFoundError:
                 logger.error(f"Python interpreter not found: {sys.executable}")
                 bot.reply_to(message_obj_for_reply, f"❌ Python interpreter '{sys.executable}' not found.")
                 return
            except Exception as e:
                 logger.error(f"Pre-check error {script_key}: {e}", exc_info=True)
                 bot.reply_to(message_obj_for_reply, f"❌ Pre-check error '{file_name}': {e}")
                 return
            finally:
                 if check_proc and check_proc.poll() is None:
                     check_proc.kill(); check_proc.communicate()

        logger.info(f"Starting long-run Python {script_key}")
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None; process = None
        try:
            log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
             logger.error(f"Log open failed {log_file_path}: {e}", exc_info=True)
             bot.reply_to(message_obj_for_reply, f"❌ Log open failed: {e}")
             return
        try:
            startupinfo = None; creationflags = 0
            if os.name == 'nt':
                 startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                 startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                [sys.executable, script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
                stdin=subprocess.PIPE, startupinfo=startupinfo, creationflags=creationflags,
                encoding='utf-8', errors='ignore'
            )
            logger.info(f"Started Python PID {process.pid} for {script_key}")
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id,
                'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder,
                'type': 'py', 'script_key': script_key
            }
            auto_restart_tracker.pop(script_key, None)
            bot.reply_to(message_obj_for_reply, f"✅ Python `{file_name}` started! (PID: {process.pid})")
        except FileNotFoundError:
             logger.error(f"Python not found {script_key}")
             bot.reply_to(message_obj_for_reply, f"❌ Python interpreter '{sys.executable}' not found.")
             if log_file and not log_file.closed: log_file.close()
             if script_key in bot_scripts: del bot_scripts[script_key]
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            error_msg = f"❌ Start error `{file_name}`: {str(e)}"
            logger.error(error_msg, exc_info=True)
            bot.reply_to(message_obj_for_reply, error_msg)
            if process and process.poll() is None:
                 kill_process_tree({'process': process, 'log_file': log_file, 'script_key': script_key})
            if script_key in bot_scripts: del bot_scripts[script_key]
    except Exception as e:
        error_msg = f"❌ Unexpected run error `{file_name}`: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message_obj_for_reply, error_msg)
        if script_key in bot_scripts:
             kill_process_tree(bot_scripts[script_key])
             del bot_scripts[script_key]

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    """Run JS script (original logic preserved)."""
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed '{file_name}' after {max_attempts} attempts.")
        return

    folder_name = _extract_folder_name(script_owner_id, user_folder)
    script_key = f"{script_owner_id}|{folder_name}|{file_name}"
    logger.info(f"JS Attempt {attempt}: {script_path} (Key: {script_key})")
    try:
        if not os.path.exists(script_path):
             bot.reply_to(message_obj_for_reply, f"❌ JS not found: `{script_path}`!")
             logger.error(f"JS missing: {script_path} for {script_owner_id}")
             if script_owner_id in user_files:
                 user_files[script_owner_id] = [f for f in user_files.get(script_owner_id, []) if f[0] != file_name]
             remove_user_file_db(script_owner_id, file_name)
             return

        if attempt == 1:
            check_command = ['node', script_path]
            logger.info(f"JS pre-check: {' '.join(check_command)}")
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode
                logger.info(f"JS pre-check RC: {return_code}. Stderr: {stderr[:200]}...")
                if return_code != 0 and stderr:
                    match_js = re.search(r"Cannot find module '(.+?)'", stderr)
                    if match_js:
                        module_name = match_js.group(1).strip().strip("'\"")
                        if not module_name.startswith('.') and not module_name.startswith('/'):
                             logger.info(f"Missing Node module: {module_name}")
                             if attempt_install_npm(module_name, user_folder, message_obj_for_reply):
                                 bot.reply_to(message_obj_for_reply, f"🔄 NPM OK. Retrying '{file_name}'...")
                                 time.sleep(2)
                                 threading.Thread(target=run_js_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                                 return
                             else:
                                 bot.reply_to(message_obj_for_reply, f"❌ NPM failed. Cannot run '{file_name}'.")
                                 return
                        else:
                            logger.info(f"Skipping npm for relative: {module_name}")
                    error_summary = stderr[:500]
                    bot.reply_to(message_obj_for_reply, f"❌ JS pre-check error '{file_name}':\n```\n{error_summary}\n```", parse_mode='Markdown')
                    return
            except subprocess.TimeoutExpired:
                logger.info("JS pre-check timed out. Proceeding.")
                if check_proc and check_proc.poll() is None:
                    check_proc.kill(); check_proc.communicate()
            except FileNotFoundError:
                 bot.reply_to(message_obj_for_reply, "❌ 'node' not found. Install Node.js.")
                 return
            except Exception as e:
                 logger.error(f"JS pre-check error {script_key}: {e}", exc_info=True)
                 bot.reply_to(message_obj_for_reply, f"❌ JS pre-check error '{file_name}': {e}")
                 return
            finally:
                 if check_proc and check_proc.poll() is None:
                     check_proc.kill(); check_proc.communicate()

        logger.info(f"Starting long-run JS {script_key}")
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None; process = None
        try:
            log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Log open failed {log_file_path}: {e}", exc_info=True)
            bot.reply_to(message_obj_for_reply, f"❌ Log open failed: {e}")
            return
        try:
            startupinfo = None; creationflags = 0
            if os.name == 'nt':
                 startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                 startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                ['node', script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
                stdin=subprocess.PIPE, startupinfo=startupinfo, creationflags=creationflags,
                encoding='utf-8', errors='ignore'
            )
            logger.info(f"Started JS PID {process.pid} for {script_key}")
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id,
                'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder,
                'type': 'js', 'script_key': script_key
            }
            auto_restart_tracker.pop(script_key, None)
            bot.reply_to(message_obj_for_reply, f"✅ JS `{file_name}` started! (PID: {process.pid})")
        except FileNotFoundError:
             bot.reply_to(message_obj_for_reply, "❌ 'node' not found.")
             if log_file and not log_file.closed: log_file.close()
             if script_key in bot_scripts: del bot_scripts[script_key]
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            error_msg = f"❌ JS start error `{file_name}`: {str(e)}"
            logger.error(error_msg, exc_info=True)
            bot.reply_to(message_obj_for_reply, error_msg)
            if process and process.poll() is None:
                 kill_process_tree({'process': process, 'log_file': log_file, 'script_key': script_key})
            if script_key in bot_scripts: del bot_scripts[script_key]
    except Exception as e:
        error_msg = f"❌ Unexpected JS run error `{file_name}`: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message_obj_for_reply, error_msg)
        if script_key in bot_scripts:
             kill_process_tree(bot_scripts[script_key])
             del bot_scripts[script_key]

# ============================================================
# --- Map Telegram import names to PyPI packages (FULL original) ---
# ============================================================
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI',
    'telegram': 'python-telegram-bot',
    'python_telegram_bot': 'python-telegram-bot',
    'aiogram': 'aiogram',
    'pyrogram': 'pyrogram',
    'telethon': 'telethon',
    'telethon.sync': 'telethon',
    'from telethon.sync import telegramclient': 'telethon',
    'telepot': 'telepot',
    'pytg': 'pytg',
    'tgcrypto': 'tgcrypto',
    'telegram_upload': 'telegram-upload',
    'telegram_send': 'telegram-send',
    'telegram_text': 'telegram-text',
    'mtproto': 'telegram-mtproto',
    'tl': 'telethon',
    'telegram_utils': 'telegram-utils',
    'telegram_logger': 'telegram-logger',
    'telegram_handlers': 'python-telegram-handlers',
    'telegram_redis': 'telegram-redis',
    'telegram_sqlalchemy': 'telegram-sqlalchemy',
    'telegram_payment': 'telegram-payment',
    'telegram_shop': 'telegram-shop-sdk',
    'pytest_telegram': 'pytest-telegram',
    'telegram_debug': 'telegram-debug',
    'telegram_scraper': 'telegram-scraper',
    'telegram_analytics': 'telegram-analytics',
    'telegram_nlp': 'telegram-nlp-toolkit',
    'telegram_ai': 'telegram-ai',
    'telegram_api': 'telegram-api-client',
    'telegram_web': 'telegram-web-integration',
    'telegram_games': 'telegram-games',
    'telegram_quiz': 'telegram-quiz-bot',
    'telegram_ffmpeg': 'telegram-ffmpeg',
    'telegram_media': 'telegram-media-utils',
    'telegram_2fa': 'telegram-twofa',
    'telegram_crypto': 'telegram-crypto-bot',
    'telegram_i18n': 'telegram-i18n',
    'telegram_translate': 'telegram-translate',
    'bs4': 'beautifulsoup4',
    'requests': 'requests',
    'pillow': 'Pillow',
    'cv2': 'opencv-python',
    'yaml': 'PyYAML',
    'dotenv': 'python-dotenv',
    'dateutil': 'python-dateutil',
    'pandas': 'pandas',
    'numpy': 'numpy',
    'flask': 'Flask',
    'django': 'Django',
    'sqlalchemy': 'SQLAlchemy',
    'asyncio': None, 'json': None, 'datetime': None, 'os': None,
    'sys': None, 're': None, 'time': None, 'math': None, 'random': None,
    'logging': None, 'threading': None, 'subprocess': None, 'zipfile': None,
    'tempfile': None, 'shutil': None, 'sqlite3': None,
    'psutil': 'psutil', 'atexit': None
}

# ============================================================
# --- Database Operations ---
# ============================================================
DB_LOCK = threading.Lock()

def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)',
                      (user_id, file_name, file_type))
            conn.commit()
            if user_id not in user_files: user_files[user_id] = []
            user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type))
            logger.info(f"Saved file '{file_name}' ({file_type}) for user {user_id}")
        except sqlite3.Error as e: logger.error(f"❌ SQLite error saving file: {e}")
        except Exception as e: logger.error(f"❌ Unexpected saving file: {e}", exc_info=True)
        finally: conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
                if not user_files[user_id]: del user_files[user_id]
            logger.info(f"Removed file '{file_name}' for user {user_id}")
        except sqlite3.Error as e: logger.error(f"❌ SQLite error removing file: {e}")
        except Exception as e: logger.error(f"❌ Unexpected removing file: {e}", exc_info=True)
        finally: conn.close()

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO active_users (user_id) VALUES (?)', (user_id,))
            conn.commit()
            logger.info(f"Active user {user_id} added")
        except sqlite3.Error as e: logger.error(f"❌ SQLite error adding user: {e}")
        except Exception as e: logger.error(f"❌ Unexpected adding user: {e}", exc_info=True)
        finally: conn.close()

def save_subscription(user_id, expiry, file_limit=None):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            expiry_str = expiry.isoformat()
            c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry, file_limit) VALUES (?, ?, ?)',
                      (user_id, expiry_str, file_limit))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry, 'file_limit': file_limit}
            logger.info(f"Saved sub for {user_id}, expiry {expiry_str}, limit {file_limit}")
        except sqlite3.Error as e: logger.error(f"❌ SQLite sub error: {e}")
        except Exception as e: logger.error(f"❌ Unexpected sub: {e}", exc_info=True)
        finally: conn.close()

def save_user_custom_limit(user_id, file_limit):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_custom_limits (user_id, file_limit) VALUES (?, ?)',
                      (user_id, file_limit))
            conn.commit()
            user_custom_limits[user_id] = file_limit
            logger.info(f"Custom limit {file_limit} for {user_id}")
        except sqlite3.Error as e: logger.error(f"❌ SQLite limit error: {e}")
        except Exception as e: logger.error(f"❌ Unexpected limit: {e}", exc_info=True)
        finally: conn.close()

def remove_user_custom_limit_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_custom_limits WHERE user_id = ?', (user_id,))
            conn.commit()
            user_custom_limits.pop(user_id, None)
            logger.info(f"Removed custom limit for {user_id}")
        except Exception as e: logger.error(f"❌ Error removing limit: {e}", exc_info=True)
        finally: conn.close()

def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_subscriptions: del user_subscriptions[user_id]
            logger.info(f"Removed sub for {user_id}")
        except sqlite3.Error as e: logger.error(f"❌ SQLite sub remove: {e}")
        except Exception as e: logger.error(f"❌ Unexpected sub remove: {e}", exc_info=True)
        finally: conn.close()

def add_admin_db(admin_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (admin_id,))
            conn.commit()
            admin_ids.add(admin_id)
            logger.info(f"Admin {admin_id} added")
        except sqlite3.Error as e: logger.error(f"❌ SQLite admin add: {e}")
        except Exception as e: logger.error(f"❌ Unexpected admin add: {e}", exc_info=True)
        finally: conn.close()

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID:
        logger.warning("Cannot remove OWNER_ID.")
        return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        removed = False
        try:
            c.execute('SELECT 1 FROM admins WHERE user_id = ?', (admin_id,))
            if c.fetchone():
                c.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
                conn.commit()
                removed = c.rowcount > 0
                if removed: admin_ids.discard(admin_id); logger.info(f"Admin {admin_id} removed")
            else:
                admin_ids.discard(admin_id)
            return removed
        except sqlite3.Error as e: logger.error(f"❌ SQLite admin remove: {e}"); return False
        except Exception as e: logger.error(f"❌ Unexpected admin remove: {e}", exc_info=True); return False
        finally: conn.close()

# 🆕 Ban DB operations
def ban_user_db(user_id, reason, name, username):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO banned_users (user_id, reason, name, username) VALUES (?, ?, ?, ?)',
                      (user_id, reason, name, username))
            conn.commit()
            banned_users[user_id] = {'reason': reason, 'name': name, 'username': username}
            logger.info(f"Banned user {user_id}: {reason}")
            return True
        except Exception as e:
            logger.error(f"❌ Ban error: {e}", exc_info=True)
            return False
        finally: conn.close()

def unban_user_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
            conn.commit()
            removed = c.rowcount > 0
            banned_users.pop(user_id, None)
            logger.info(f"Unbanned {user_id}")
            return removed
        except Exception as e:
            logger.error(f"❌ Unban error: {e}", exc_info=True)
            return False
        finally: conn.close()

# ============================================================
# --- Menu creation ---
# ============================================================
def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton('📢 Updates Channel', url=UPDATE_CHANNEL),
        types.InlineKeyboardButton('📤 Upload File', callback_data='upload'),
        types.InlineKeyboardButton('📂 Check Files', callback_data='check_files'),
        types.InlineKeyboardButton('⚡ Bot Speed', callback_data='speed'),
        types.InlineKeyboardButton('📞 Contact Owner', url='https://t.me/GOD_AYUSH')
    ]
    if user_id in admin_ids:
        admin_buttons = [
            types.InlineKeyboardButton('💳 Subscriptions', callback_data='subscription'),
            types.InlineKeyboardButton('📊 Statistics', callback_data='stats'),
            types.InlineKeyboardButton('🔒 Lock Bot' if not bot_locked else '🔓 Unlock Bot',
                                     callback_data='lock_bot' if not bot_locked else 'unlock_bot'),
            types.InlineKeyboardButton('📢 Broadcast', callback_data='broadcast'),
            types.InlineKeyboardButton('👑 Admin Panel', callback_data='admin_panel'),
            types.InlineKeyboardButton('🟢 Run All User Scripts', callback_data='run_all_scripts'),
            # 🆕 NEW admin buttons
            types.InlineKeyboardButton('🖥️ Hosting Dashboard', callback_data='hosting_dashboard'),
            types.InlineKeyboardButton('📈 Resource Monitor', callback_data='resource_monitor'),
            types.InlineKeyboardButton('💾 Backup All', callback_data='backup_all'),
            types.InlineKeyboardButton('♻️ Auto-Restart' + (' (ON)' if auto_restart_enabled else ' (OFF)'),
                                       callback_data='toggle_auto_restart')
        ]
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3], admin_buttons[0])
        markup.add(admin_buttons[1], admin_buttons[3])
        markup.add(admin_buttons[2], admin_buttons[5])
        markup.add(admin_buttons[6], admin_buttons[7])   # 🆕
        markup.add(admin_buttons[8], admin_buttons[9])   # 🆕
        markup.add(admin_buttons[4])
        markup.add(buttons[4])
    else:
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3])
        markup.add(types.InlineKeyboardButton('📊 Statistics', callback_data='stats'))
        markup.add(buttons[4])
    return markup

def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row_buttons_text in layout_to_use:
        btns = []
        for text in row_buttons_text:
            if text.startswith("♻️ Auto Restart"):
                text = f"♻️ Auto Restart: {'ON' if auto_restart_enabled else 'OFF'}"
            btns.append(types.KeyboardButton(text=text))
        markup.add(*btns)
    return markup

def create_control_buttons(script_owner_id, file_name, is_running=True, folder_name='__root__'):
    markup = types.InlineKeyboardMarkup(row_width=2)
    cb = f"{script_owner_id}_{folder_name}|{file_name}"
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{cb}'),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{cb}')
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{cb}'),
            types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{cb}')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{cb}'),
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{cb}')
        )
        markup.row(
            types.InlineKeyboardButton("📜 View Logs", callback_data=f'logs_{cb}')
        )
    # 🆕 Per-script backup
    markup.add(types.InlineKeyboardButton("💾 Backup", callback_data=f'backup_file_{cb}'))
    markup.add(types.InlineKeyboardButton("🔙 Back to Folders", callback_data='check_files'))
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Admin', callback_data='add_admin'),
        types.InlineKeyboardButton('➖ Remove Admin', callback_data='remove_admin')
    )
    markup.row(types.InlineKeyboardButton('📋 List Admins', callback_data='list_admins'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Premium', callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ Remove Premium', callback_data='remove_subscription')
    )
    markup.row(
        types.InlineKeyboardButton('✏️ Edit Sub', callback_data='edit_subscription'),
        types.InlineKeyboardButton('🔍 Check Sub', callback_data='check_subscription')
    )
    markup.row(
        types.InlineKeyboardButton('🔢 Set User Limit', callback_data='set_user_limit'),
        types.InlineKeyboardButton('📋 List Premium', callback_data='list_premium')
    )
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

# ============================================================
# --- File Handling (original preserved + 🆕 Backup) ---
# ============================================================
def handle_zip_file(downloaded_file_content, file_name_zip, message, user_folder=None):
    user_id = message.from_user.id
    if user_folder is None:
        user_folder = get_user_folder(user_id)
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
        logger.info(f"Temp dir: {temp_dir}")
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as new_file: new_file.write(downloaded_file_content)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.infolist():
                member_path = os.path.abspath(os.path.join(temp_dir, member.filename))
                if not member_path.startswith(os.path.abspath(temp_dir)):
                    raise zipfile.BadZipFile(f"Unsafe path: {member.filename}")
            zip_ref.extractall(temp_dir)
            logger.info(f"Extracted to {temp_dir}")

        extracted_items = os.listdir(temp_dir)
        py_files = [f for f in extracted_items if f.endswith('.py')]
        js_files = [f for f in extracted_items if f.endswith('.js')]
        req_file = 'requirements.txt' if 'requirements.txt' in extracted_items else None
        pkg_json = 'package.json' if 'package.json' in extracted_items else None

        if req_file:
            req_path = os.path.join(temp_dir, req_file)
            logger.info(f"requirements.txt found: {req_path}")
            bot.reply_to(message, f"🔄 Installing deps from `{req_file}`...")
            req_install_methods = [
                [sys.executable, '-m', 'pip', 'install', '-r', req_path],
                [sys.executable, '-m', 'pip', 'install', '--user', '-r', req_path],
                [sys.executable, '-m', 'pip', 'install', '--break-system-packages', '-r', req_path],
            ]
            req_installed = False
            last_req_error = ""
            for cmd in req_install_methods:
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore')
                    if result.returncode == 0:
                        bot.reply_to(message, f"✅ Python deps installed.")
                        req_installed = True; break
                    last_req_error = result.stderr or result.stdout
                except Exception as e:
                    last_req_error = str(e)
            if not req_installed:
                error_msg = f"❌ Failed deps install.\nLog:\n```\n{last_req_error[:800]}\n```"
                if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n..."
                bot.reply_to(message, error_msg, parse_mode='Markdown'); return

        if pkg_json:
            logger.info(f"package.json found, npm install")
            bot.reply_to(message, f"🔄 Installing Node deps...")
            try:
                result = subprocess.run(['npm', 'install'], capture_output=True, text=True, check=True, cwd=temp_dir, encoding='utf-8', errors='ignore')
                bot.reply_to(message, f"✅ Node deps installed.")
            except FileNotFoundError:
                bot.reply_to(message, "❌ npm not found."); return
            except subprocess.CalledProcessError as e:
                error_msg = f"❌ Node deps failed.\nLog:\n```\n{e.stderr or e.stdout}\n```"
                if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n..."
                bot.reply_to(message, error_msg, parse_mode='Markdown'); return
            except Exception as e:
                 bot.reply_to(message, f"❌ Error: {e}"); return

        main_script_name = None; file_type = None
        preferred_py = ['main.py', 'bot.py', 'app.py']
        preferred_js = ['index.js', 'main.js', 'bot.js', 'app.js']
        for p in preferred_py:
            if p in py_files: main_script_name = p; file_type = 'py'; break
        if not main_script_name:
             for p in preferred_js:
                 if p in js_files: main_script_name = p; file_type = 'js'; break
        if not main_script_name:
            if py_files: main_script_name = py_files[0]; file_type = 'py'
            elif js_files: main_script_name = js_files[0]; file_type = 'js'
        if not main_script_name:
            bot.reply_to(message, "❌ No `.py` or `.js` found!"); return

        logger.info(f"Moving files from {temp_dir} → {user_folder}")
        for item_name in os.listdir(temp_dir):
            src_path = os.path.join(temp_dir, item_name)
            dest_path = os.path.join(user_folder, item_name)
            if os.path.isdir(dest_path): shutil.rmtree(dest_path)
            elif os.path.exists(dest_path): os.remove(dest_path)
            shutil.move(src_path, dest_path)

        save_user_file(user_id, main_script_name, file_type)
        main_script_path = os.path.join(user_folder, main_script_name)
        bot.reply_to(message, f"✅ Extracted. Starting `{main_script_name}`...", parse_mode='Markdown')

        if file_type == 'py':
             threading.Thread(target=run_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()
        elif file_type == 'js':
             threading.Thread(target=run_js_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()

    except zipfile.BadZipFile as e:
        bot.reply_to(message, f"❌ Invalid ZIP: {e}")
    except Exception as e:
        logger.error(f"❌ ZIP error: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except Exception as e: logger.error(f"Temp clean error: {e}", exc_info=True)

def handle_js_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'js')
        threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        logger.error(f"❌ JS handle error: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")

STDLIB_MODULES = set(sys.stdlib_module_names) if hasattr(sys, 'stdlib_module_names') else {
    'os', 'sys', 're', 'io', 'json', 'math', 'time', 'random', 'string',
    'collections', 'functools', 'itertools', 'operator', 'pathlib', 'shutil',
    'copy', 'datetime', 'calendar', 'hashlib', 'hmac', 'secrets', 'struct',
    'socket', 'ssl', 'http', 'urllib', 'email', 'html', 'xml', 'csv',
    'sqlite3', 'pickle', 'shelve', 'gzip', 'zipfile', 'tarfile', 'tempfile',
    'threading', 'multiprocessing', 'subprocess', 'signal', 'logging',
    'unittest', 'doctest', 'pdb', 'profile', 'timeit', 'traceback',
    'inspect', 'ast', 'dis', 'types', 'typing', 'abc', 'contextlib',
    'dataclasses', 'enum', 'warnings', 'weakref', 'gc', 'platform',
    'argparse', 'getopt', 'cmd', 'readline', 'glob', 'fnmatch',
    'base64', 'binascii', 'codecs', 'unicodedata', 'textwrap', 'pprint',
    'queue', 'heapq', 'bisect', 'array', 'decimal', 'fractions', 'statistics',
    'builtins', '__future__', 'importlib', 'pkgutil', 'concurrent',
    'asyncio', 'selectors', 'select', 'socketserver', 'xmlrpc', 'ftplib',
    'smtplib', 'poplib', 'imaplib', 'telnetlib', 'uuid', 'ipaddress',
    'ctypes', 'mmap', 'msvcrt', 'winreg', 'winsound', 'posix', 'pty',
    'tty', 'termios', 'resource', 'grp', 'pwd', 'nis', 'syslog',
    'token', 'tokenize', 'keyword', 'symbol', 'compileall', 'py_compile',
    'cProfile', 'pstats', 'trace', 'code', 'codeop', 'zipimport',
    'antigravity', 'this', '_thread', 'atexit', 'sched', 'errno',
}

def auto_install_imports_from_py(file_path, message):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            source = f.read()
    except Exception as e:
        logger.warning(f"Could not read for import scan: {e}")
        return

    import_lines = re.findall(r'^\s*(?:import|from)\s+([\w]+)', source, re.MULTILINE)
    packages_to_try = set()
    for pkg in import_lines:
        top = pkg.split('.')[0].lower()
        if top and top not in STDLIB_MODULES and len(top) > 1:
            packages_to_try.add(top)

    if not packages_to_try:
        return

    missing = []
    for pkg in packages_to_try:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if not missing:
        return

    bot.reply_to(message,
        f"🔍 Missing: `{'`, `'.join(missing)}`\n🔄 Installing...", parse_mode='Markdown')

    installed = []; failed = []
    for pkg in missing:
        mapped = TELEGRAM_MODULES.get(pkg, pkg)
        if mapped is None: continue
        cmd = [sys.executable, '-m', 'pip', 'install', '--break-system-packages', '--quiet', mapped]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            installed.append(mapped)
        else:
            failed.append(mapped)

    lines = []
    if installed: lines.append(f"✅ Installed: `{'`, `'.join(installed)}`")
    if failed: lines.append(f"⚠️ Failed: `{'`, `'.join(failed)}`")
    if lines: bot.reply_to(message, '\n'.join(lines), parse_mode='Markdown')

def handle_py_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'py')
        auto_install_imports_from_py(file_path, message)
        threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        logger.error(f"❌ Py handle error: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")

# ============================================================
# 🆕 BACKUP / RESTORE SYSTEM
# ============================================================
def create_backup_for_user(user_id):
    """Create ZIP backup of a user's scripts folder."""
    user_folder = get_user_folder(user_id)
    if not os.path.exists(user_folder) or not os.listdir(user_folder):
        return None
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"backup_{user_id}_{timestamp}.zip"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    try:
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as z:
            for root, dirs, files in os.walk(user_folder):
                for f in files:
                    if f.endswith('.log'): continue
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, user_folder)
                    z.write(full, rel)
        logger.info(f"Backup: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Backup error: {e}", exc_info=True)
        return None

def create_full_backup():
    """Create ZIP backup of ALL users + DB."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"full_backup_{timestamp}.zip"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    try:
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as z:
            for uid in user_files.keys():
                user_folder = get_user_folder(uid)
                if not os.path.exists(user_folder): continue
                for root, dirs, files in os.walk(user_folder):
                    for f in files:
                        if f.endswith('.log'): continue
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, UPLOAD_BOTS_DIR)
                        z.write(full, rel)
            if os.path.exists(DATABASE_PATH):
                z.write(DATABASE_PATH, 'bot_data.db')
        logger.info(f"Full backup: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Full backup error: {e}", exc_info=True)
        return None

def create_single_file_backup(target_uid, folder, fname):
    """Create ZIP backup of single script + its log."""
    base = get_user_folder(target_uid)
    uf = os.path.join(base, folder) if folder != '__root__' else base
    fp = os.path.join(uf, fname)
    if not os.path.exists(fp):
        return None
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    bname = f"backup_{target_uid}_{os.path.splitext(fname)[0]}_{timestamp}.zip"
    bpath = os.path.join(BACKUP_DIR, bname)
    try:
        with zipfile.ZipFile(bpath, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(fp, os.path.join(folder, fname))
            lp = os.path.join(uf, f"{os.path.splitext(fname)[0]}.log")
            if os.path.exists(lp):
                z.write(lp, os.path.join(folder, os.path.basename(lp)))
        return bpath
    except Exception as e:
        logger.error(f"Single backup error: {e}", exc_info=True)
        return None

def restore_from_backup(zip_path, target_user_id=None):
    """Restore scripts from ZIP backup. If target_user_id given, restore only that user."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            for m in z.infolist():
                mp = os.path.abspath(os.path.join(UPLOAD_BOTS_DIR, m.filename))
                if not mp.startswith(os.path.abspath(UPLOAD_BOTS_DIR)):
                    raise zipfile.BadZipFile(f"Unsafe path: {m.filename}")
            z.extractall(UPLOAD_BOTS_DIR)

        # Re-scan and re-register
        for uid_dir in os.listdir(UPLOAD_BOTS_DIR):
            full = os.path.join(UPLOAD_BOTS_DIR, uid_dir)
            if not os.path.isdir(full) or not uid_dir.isdigit():
                continue
            uid = int(uid_dir)
            if target_user_id and uid != target_user_id:
                continue
            for f in os.listdir(full):
                p = os.path.join(full, f)
                if os.path.isfile(p) and f.endswith('.py'):
                    save_user_file(uid, f, 'py')
                elif os.path.isfile(p) and f.endswith('.js'):
                    save_user_file(uid, f, 'js')
            for sub in os.listdir(full):
                sp = os.path.join(full, sub)
                if os.path.isdir(sp):
                    for f in os.listdir(sp):
                        if f.endswith('.py'):
                            save_user_file(uid, f, 'py')
                        elif f.endswith('.js'):
                            save_user_file(uid, f, 'js')
        logger.info(f"Restore complete from {zip_path}")
        return True
    except Exception as e:
        logger.error(f"Restore error: {e}", exc_info=True)
        return False

# ============================================================
# --- Logic Functions ---
# ============================================================
def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name
    user_username = message.from_user.username

    logger.info(f"Welcome: user_id={user_id}, @{user_username}")

    if user_id in banned_users:
        bot.send_message(chat_id, f"🚫 You are banned.\nReason: {banned_users[user_id]['reason']}")
        return

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "⚠️ Bot locked by admin. Try later.")
        return

    user_bio = "Could not fetch bio"; photo_file_id = None
    try: user_bio = bot.get_chat(user_id).bio or "No bio"
    except Exception: pass
    try:
        user_profile_photos = bot.get_user_profile_photos(user_id, limit=1)
        if user_profile_photos.photos: photo_file_id = user_profile_photos.photos[0][-1].file_id
    except Exception: pass

    if user_id not in active_users:
        add_active_user(user_id)
        try:
            owner_notification = (f"🎉 New user!\n👤 Name: {user_name}\n✳️ User: @{user_username or 'N/A'}\n"
                                  f"🆔 ID: `{user_id}`\n📝 Bio: {user_bio}")
            bot.send_message(OWNER_ID, owner_notification, parse_mode='Markdown')
            if photo_file_id: bot.send_photo(OWNER_ID, photo_file_id, caption=f"Pic of new user {user_id}")
        except Exception as e: logger.error(f"⚠️ Owner notify failed: {e}")

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    expiry_info = ""
    if user_id == OWNER_ID: user_status = "👑 Owner"
    elif user_id in admin_ids: user_status = "🛡️ Admin"
    elif user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            user_status = "⭐ Premium"; days_left = (expiry_date - datetime.now()).days
            expiry_info = f"\n⏳ Subscription expires in: {days_left} days"
        else: user_status = "🆓 Free User (Expired Sub)"; remove_subscription_db(user_id)
    else: user_status = "🆓 Free User"

    welcome_msg_text = (f"〽️ Welcome, {user_name}!\n\n🆔 Your User ID: `{user_id}`\n"
                        f"✳️ Username: `@{user_username or 'Not set'}`\n"
                        f"🔰 Your Status: {user_status}{expiry_info}\n"
                        f"📁 Files Uploaded: {current_files} / {limit_str}\n\n"
                        f"🤖 Host & run Python (`.py`) or JS (`.js`) scripts.\n"
                        f"   Upload single scripts or `.zip` archives.\n\n"
                        f"👇 Use buttons or type commands.")
    main_reply_markup = create_reply_keyboard_main_menu(user_id)
    try:
        if photo_file_id: bot.send_photo(chat_id, photo_file_id)
        bot.send_message(chat_id, welcome_msg_text, reply_markup=main_reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error sending welcome: {e}", exc_info=True)
        try: bot.send_message(chat_id, welcome_msg_text, reply_markup=main_reply_markup, parse_mode='Markdown')
        except Exception as fallback_e: logger.error(f"Fallback failed: {fallback_e}")

def _logic_updates_channel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📢 Updates Channel', url=UPDATE_CHANNEL))
    bot.reply_to(message, "Visit our Updates Channel:", reply_markup=markup)

def _logic_upload_file(message):
    user_id = message.from_user.id
    if user_id in banned_users:
        bot.reply_to(message, "🚫 You are banned."); return
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked, cannot accept files."); return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, f"⚠️ File limit ({current_files}/{limit_str}) reached. Delete files first.")
        return
    msg = bot.reply_to(message, "📁 Pehle apni file ke liye ek *folder name* type karo:\n\n(Sirf letters, numbers, underscore \\_ allowed. Example: `my_bot`)\n\n/cancel - cancel karne ke liye", parse_mode='Markdown')
    bot.register_next_step_handler(msg, _process_folder_name_step)

KNOWN_BUTTON_TEXTS = {
    "📢 Updates Channel", "📤 Upload File", "📂 Check Files",
    "⚡ Bot Speed", "📊 Statistics", "📞 Contact Owner",
    "💳 Subscriptions", "📢 Broadcast", "🔒 Lock Bot",
    "🟢 Running All Code", "👑 Admin Panel",
    "🖥️ Hosting Dashboard", "📈 Resource Monitor", "💾 Backup All"
}

def _process_folder_name_step(message):
    user_id = message.from_user.id

    if message.text and (
        message.text.strip().startswith('/') or
        message.text.strip() in KNOWN_BUTTON_TEXTS or
        message.text.strip().startswith("♻️ Auto Restart")
    ):
        users_pending_folder.pop(user_id, None)
        users_awaiting_upload.discard(user_id)
        text = message.text.strip().lower()
        if text == '/cancel':
            bot.reply_to(message, "❌ Upload cancel ho gaya.\n\n👇 Niche se koi button press karo.",
                         reply_markup=create_reply_keyboard_main_menu(user_id))
            return
        raw_text = message.text.strip()
        if raw_text.startswith("♻️ Auto Restart"):
            _logic_toggle_auto_restart(message)
            return
        logic_func = BUTTON_TEXT_TO_LOGIC.get(raw_text)
        if logic_func:
            logic_func(message)
        elif text.startswith('/start'):
            _logic_send_welcome(message)
        return

    if not message.text:
        msg = bot.reply_to(message, "⚠️ Sirf text mein folder name do. /cancel")
        bot.register_next_step_handler(msg, _process_folder_name_step)
        return
    folder_name = message.text.strip()
    if not re.match(r'^[\w\-. ]+$', folder_name) or len(folder_name) > 50:
        msg = bot.reply_to(message, "⚠️ Invalid folder name!\nSirf letters, numbers, space, `-`, `_`, `.` allowed. (Max 50)\n\n/cancel", parse_mode='Markdown')
        bot.register_next_step_handler(msg, _process_folder_name_step)
        return
    users_pending_folder[user_id] = folder_name
    users_awaiting_upload.add(user_id)
    bot.reply_to(message, f"✅ Folder name set: `{folder_name}`\n\n📤 Ab apni Python (`.py`), JS (`.js`), ya ZIP (`.zip`) bhejo!", parse_mode='Markdown')

def _logic_check_files(message):
    user_id = message.from_user.id
    folders = _get_user_folder_names(user_id)
    if not folders:
        bot.reply_to(message, "📂 Koi folders nahi. Upload File button se upload karo!")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for folder in folders:
        files_in = _get_files_in_folder(user_id, folder)
        running_count = sum(1 for fn, _ in files_in if is_bot_running(user_id, fn, folder))
        total = len(files_in)
        status_icon = "🟢" if running_count > 0 else "📁"
        btn_text = f"{status_icon} {folder}  ({running_count} running / {total} files)"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'fold_{user_id}_{folder}'))
    bot.reply_to(message, "📂 Tumhare Folders:\nFolder pe click karo files dekhne ke liye.", reply_markup=markup)

def _logic_bot_speed(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    start_time_ping = time.time()
    wait_msg = bot.reply_to(message, "🏃 Testing speed...")
    try:
        bot.send_chat_action(chat_id, 'typing')
        response_time = round((time.time() - start_time_ping) * 1000, 2)
        status = "🔓 Unlocked" if not bot_locked else "🔒 Locked"
        if user_id == OWNER_ID: user_level = "👑 Owner"
        elif user_id in admin_ids: user_level = "🛡️ Admin"
        elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now(): user_level = "⭐ Premium"
        else: user_level = "🆓 Free User"
        speed_msg = (f"⚡ Bot Speed & Status:\n\n⏱️ API Response Time: {response_time} ms\n"
                     f"🚦 Bot Status: {status}\n"
                     f"♻️ Auto-Restart: {'ON' if auto_restart_enabled else 'OFF'}\n"
                     f"👤 Your Level: {user_level}")
        bot.edit_message_text(speed_msg, chat_id, wait_msg.message_id)
    except Exception as e:
        logger.error(f"Speed error: {e}", exc_info=True)
        bot.edit_message_text("❌ Error during speed test.", chat_id, wait_msg.message_id)

def _logic_contact_owner(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/GOD_AYUSH'))
    bot.reply_to(message, "Click to contact Owner:", reply_markup=markup)

# --- Admin Logic Functions ---
def _logic_subscriptions_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    bot.reply_to(message, "💳 Subscription Management\nUse inline buttons.", reply_markup=create_subscription_menu())

def _logic_statistics(message):
    user_id = message.from_user.id
    total_users = len(active_users)
    total_files_records = sum(len(files) for files in user_files.values())
    running_bots_count = 0
    user_running_bots = 0

    for script_key_iter, script_info_iter in list(bot_scripts.items()):
        parts = script_key_iter.split('|')
        s_owner_id = parts[0] if parts else '0'
        s_folder = parts[1] if len(parts) > 1 else None
        if is_bot_running(int(s_owner_id), script_info_iter['file_name'], s_folder):
            running_bots_count += 1
            if int(s_owner_id) == user_id:
                user_running_bots += 1

    stats_msg_base = (f"📊 Bot Statistics:\n\n"
                      f"👥 Total Users: {total_users}\n"
                      f"📂 Total File Records: {total_files_records}\n"
                      f"🟢 Total Active Bots: {running_bots_count}\n")

    if user_id in admin_ids:
        stats_msg_admin = (f"🔒 Bot Status: {'🔴 Locked' if bot_locked else '🟢 Unlocked'}\n"
                           f"♻️ Auto-Restart: {'✅ ON' if auto_restart_enabled else '❌ OFF'}\n"
                           f"🤖 Your Running Bots: {user_running_bots}")
        stats_msg = stats_msg_base + stats_msg_admin
    else:
        stats_msg = stats_msg_base + f"🤖 Your Running Bots: {user_running_bots}"

    bot.reply_to(message, stats_msg)

def _logic_broadcast_init(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    msg = bot.reply_to(message, "📢 Send message to broadcast to all active users.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def _logic_toggle_lock_bot(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    global bot_locked
    bot_locked = not bot_locked
    status = "locked" if bot_locked else "unlocked"
    logger.warning(f"Bot {status} by Admin {message.from_user.id}")
    bot.reply_to(message, f"🔒 Bot has been {status}.")

def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    bot.reply_to(message, "👑 Admin Panel\nManage admins.", reply_markup=create_admin_panel())

def _logic_run_all_scripts(message_or_call):
    if isinstance(message_or_call, telebot.types.Message):
        admin_user_id = message_or_call.from_user.id
        admin_chat_id = message_or_call.chat.id
        reply_func = lambda text, **kwargs: bot.reply_to(message_or_call, text, **kwargs)
        admin_message_obj_for_script_runner = message_or_call
    elif isinstance(message_or_call, telebot.types.CallbackQuery):
        admin_user_id = message_or_call.from_user.id
        admin_chat_id = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)
        reply_func = lambda text, **kwargs: bot.send_message(admin_chat_id, text, **kwargs)
        admin_message_obj_for_script_runner = message_or_call.message
    else:
        logger.error("Invalid arg for _logic_run_all_scripts")
        return

    if admin_user_id not in admin_ids:
        reply_func("⚠️ Admin permissions required.")
        return

    reply_func("⏳ Starting all user scripts...")
    logger.info(f"Admin {admin_user_id} initiated run-all from {admin_chat_id}.")

    started_count = 0; attempted_users = 0; skipped_files = 0; error_files_details = []
    all_user_files_snapshot = dict(user_files)

    for target_user_id, files_for_user in all_user_files_snapshot.items():
        if not files_for_user: continue
        attempted_users += 1
        logger.info(f"Processing user {target_user_id}...")
        user_folder = get_user_folder(target_user_id)

        for file_name, file_type in files_for_user:
            if not is_bot_running(target_user_id, file_name):
                file_path = os.path.join(user_folder, file_name)
                if os.path.exists(file_path):
                    try:
                        if file_type == 'py':
                            threading.Thread(target=run_script, args=(file_path, target_user_id, user_folder, file_name, admin_message_obj_for_script_runner)).start()
                            started_count += 1
                        elif file_type == 'js':
                            threading.Thread(target=run_js_script, args=(file_path, target_user_id, user_folder, file_name, admin_message_obj_for_script_runner)).start()
                            started_count += 1
                        else:
                            error_files_details.append(f"`{file_name}` (User {target_user_id}) - Unknown type")
                            skipped_files += 1
                        time.sleep(0.7)
                    except Exception as e:
                        logger.error(f"Queue start error {file_name}: {e}")
                        error_files_details.append(f"`{file_name}` (User {target_user_id}) - Start error")
                        skipped_files += 1
                else:
                    error_files_details.append(f"`{file_name}` (User {target_user_id}) - File not found")
                    skipped_files += 1

    summary_msg = (f"✅ All Users' Scripts - Processing Complete:\n\n"
                   f"▶️ Attempted to start: {started_count} scripts.\n"
                   f"👥 Users processed: {attempted_users}.\n")
    if skipped_files > 0:
        summary_msg += f"⚠️ Skipped/Error files: {skipped_files}\n"
        if error_files_details:
             summary_msg += "Details (first 5):\n" + "\n".join([f"  - {err}" for err in error_files_details[:5]])
             if len(error_files_details) > 5: summary_msg += "\n  ... and more (check logs)."

    reply_func(summary_msg, parse_mode='Markdown')
    logger.info(f"Run-all finished. Admin: {admin_user_id}. Started: {started_count}. Skipped: {skipped_files}")

# ============================================================
# 🆕 NEW Logic functions
# ============================================================
def _logic_hosting_dashboard(message_or_call):
    """Dashboard showing all running/stopped scripts overview."""
    if isinstance(message_or_call, telebot.types.Message):
        uid = message_or_call.from_user.id
        reply = lambda t, **k: bot.reply_to(message_or_call, t, **k)
    else:
        uid = message_or_call.from_user.id
        bot.answer_callback_query(message_or_call.id)
        reply = lambda t, **k: bot.send_message(message_or_call.message.chat.id, t, **k)

    if uid not in admin_ids:
        reply("⚠️ Admin only."); return

    running = stopped = 0
    per_user = {}
    for k, info in list(bot_scripts.items()):
        p = k.split('|')
        if len(p) < 3: continue
        oid = int(p[0]); folder = p[1]; fn = p[2]
        if is_bot_running(oid, fn, folder):
            running += 1
            per_user.setdefault(oid, []).append(f"🟢 `{fn}` ({folder})")
        else:
            stopped += 1
            per_user.setdefault(oid, []).append(f"🔴 `{fn}` ({folder})")

    # Include idle files not in bot_scripts
    for uid2, files in user_files.items():
        for fn, ft in files:
            found = any(k.startswith(f"{uid2}|") and k.endswith(f"|{fn}") for k in bot_scripts)
            if not found:
                stopped += 1
                per_user.setdefault(uid2, []).append(f"🔴 `{fn}` (idle)")

    lines = [
        "🖥️ *Hosting Dashboard*",
        "",
        f"🟢 Running: `{running}`",
        f"🔴 Stopped: `{stopped}`",
        f"👥 Users: `{len(per_user)}`",
        f"♻️ Auto-Restart: `{'ON' if auto_restart_enabled else 'OFF'}`",
        f"🧵 Active Processes (system): `{len(psutil.pids())}`",
        ""
    ]
    count = 0
    for oid, items in per_user.items():
        if count >= 8:
            lines.append(f"... and `{len(per_user) - count}` more users")
            break
        lines.append(f"👤 User `{oid}`:")
        for it in items[:5]:
            lines.append(f"   {it}")
        if len(items) > 5:
            lines.append(f"   ... +{len(items)-5} more")
        count += 1
    reply("\n".join(lines), parse_mode='Markdown')

def _logic_resource_monitor(message_or_call):
    """CPU/RAM/Disk + per-process usage."""
    if isinstance(message_or_call, telebot.types.Message):
        uid = message_or_call.from_user.id
        reply = lambda t, **k: bot.reply_to(message_or_call, t, **k)
    else:
        uid = message_or_call.from_user.id
        bot.answer_callback_query(message_or_call.id)
        reply = lambda t, **k: bot.send_message(message_or_call.message.chat.id, t, **k)

    if uid not in admin_ids:
        reply("⚠️ Admin only."); return

    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        try: disk = psutil.disk_usage('/')
        except Exception: disk = psutil.disk_usage('C:\\')

        lines = [
            "📈 *Resource Monitor*",
            "",
            f"🖥️ CPU: `{cpu}%`",
            f"🧠 RAM: `{mem.used // (1024**2)} MB / {mem.total // (1024**2)} MB ({mem.percent}%)`",
            f"💾 Disk: `{disk.used // (1024**3)} GB / {disk.total // (1024**3)} GB ({disk.percent}%)`",
            "",
            "🤖 *Hosted Processes:*"
        ]
        procs = []
        for k, info in list(bot_scripts.items()):
            proc = info.get('process')
            if proc and proc.poll() is None:
                try:
                    p = psutil.Process(proc.pid)
                    cpu_p = p.cpu_percent(interval=0.1)
                    mem_p = p.memory_info().rss // (1024**2)
                    parts = k.split('|')
                    procs.append((parts[-1], proc.pid, cpu_p, mem_p, parts[0] if parts else '?'))
                except psutil.NoSuchProcess:
                    pass
        if not procs:
            lines.append("  (no running scripts)")
        else:
            lines.append(f"  Total: `{len(procs)}` running")
            procs.sort(key=lambda x: x[3], reverse=True)
            for name, pid, c, m, owner in procs[:8]:
                lines.append(f"  `{name}` (U{owner}) PID:{pid} CPU:{c:.1f}% RAM:{m}MB")
            if len(procs) > 8:
                lines.append(f"  ... +{len(procs) - 8} more")
        reply("\n".join(lines), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Resource monitor error: {e}", exc_info=True)
        reply(f"❌ Error: {e}")

def _logic_backup_all(message_or_call):
    """Create full backup and send as document."""
    if isinstance(message_or_call, telebot.types.Message):
        uid = message_or_call.from_user.id
        chat = message_or_call.chat.id
        reply = lambda t, **k: bot.reply_to(message_or_call, t, **k)
    else:
        uid = message_or_call.from_user.id
        chat = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)
        reply = lambda t, **k: bot.send_message(chat, t, **k)

    if uid not in admin_ids:
        reply("⚠️ Admin only."); return

    reply("💾 Creating full backup...")
    path = create_full_backup()
    if path and os.path.exists(path):
        size_kb = os.path.getsize(path) // 1024
        try:
            with open(path, 'rb') as f:
                bot.send_document(chat, f,
                                  caption=f"💾 Full Backup\nSize: {size_kb} KB\nFile: `{os.path.basename(path)}`",
                                  parse_mode='Markdown')
        except Exception as e:
            reply(f"⚠️ Backup created at `{path}` but upload failed: {e}")
    else:
        reply("❌ Backup failed. No files?")

def _logic_toggle_auto_restart(message_or_call):
    """Toggle auto-restart feature."""
    global auto_restart_enabled
    if isinstance(message_or_call, telebot.types.Message):
        uid = message_or_call.from_user.id
        reply = lambda t, **k: bot.reply_to(message_or_call, t, **k)
    else:
        uid = message_or_call.from_user.id
        bot.answer_callback_query(message_or_call.id)
        reply = lambda t, **k: bot.send_message(message_or_call.message.chat.id, t, **k)

    if uid not in admin_ids:
        reply("⚠️ Admin only."); return

    auto_restart_enabled = not auto_restart_enabled
    reply(f"♻️ Auto-Restart: *{'ON ✅' if auto_restart_enabled else 'OFF ❌'}*\n\n"
          f"Max attempts: `{MAX_AUTO_RESTARTS}` per `{RESTART_WINDOW}s` window.",
          parse_mode='Markdown')

# ============================================================
# --- Command Handlers & Text Handlers ---
# ============================================================
@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message): _logic_send_welcome(message)

@bot.message_handler(commands=['status'])
def command_show_status(message): _logic_statistics(message)

BUTTON_TEXT_TO_LOGIC = {
    "📢 Updates Channel": _logic_updates_channel,
    "📤 Upload File": _logic_upload_file,
    "📂 Check Files": _logic_check_files,
    "⚡ Bot Speed": _logic_bot_speed,
    "📞 Contact Owner": _logic_contact_owner,
    "📊 Statistics": _logic_statistics,
    "💳 Subscriptions": _logic_subscriptions_panel,
    "📢 Broadcast": _logic_broadcast_init,
    "🔒 Lock Bot": _logic_toggle_lock_bot,
    "🟢 Running All Code": _logic_run_all_scripts,
    "👑 Admin Panel": _logic_admin_panel,
    # 🆕
    "🖥️ Hosting Dashboard": _logic_hosting_dashboard,
    "📈 Resource Monitor": _logic_resource_monitor,
    "💾 Backup All": _logic_backup_all,
}

@bot.message_handler(func=lambda m: m.text and (
    m.text in BUTTON_TEXT_TO_LOGIC or (m.text or "").startswith("♻️ Auto Restart")))
def handle_button_text(message):
    if message.text.startswith("♻️ Auto Restart"):
        _logic_toggle_auto_restart(message)
        try:
            bot.send_message(message.chat.id, "Keyboard updated.",
                             reply_markup=create_reply_keyboard_main_menu(message.from_user.id))
        except Exception: pass
        return
    logic_func = BUTTON_TEXT_TO_LOGIC.get(message.text)
    if logic_func: logic_func(message)
    else: logger.warning(f"Button '{message.text}' matched but no func.")

@bot.message_handler(commands=['updateschannel'])
def command_updates_channel(message): _logic_updates_channel(message)
@bot.message_handler(commands=['uploadfile'])
def command_upload_file(message): _logic_upload_file(message)
@bot.message_handler(commands=['checkfiles'])
def command_check_files(message): _logic_check_files(message)
@bot.message_handler(commands=['botspeed'])
def command_bot_speed(message): _logic_bot_speed(message)
@bot.message_handler(commands=['contactowner'])
def command_contact_owner(message): _logic_contact_owner(message)
@bot.message_handler(commands=['subscriptions'])
def command_subscriptions(message): _logic_subscriptions_panel(message)
@bot.message_handler(commands=['statistics'])
def command_statistics(message): _logic_statistics(message)
@bot.message_handler(commands=['broadcast'])
def command_broadcast(message): _logic_broadcast_init(message)
@bot.message_handler(commands=['lockbot'])
def command_lock_bot(message): _logic_toggle_lock_bot(message)
@bot.message_handler(commands=['adminpanel'])
def command_admin_panel(message): _logic_admin_panel(message)
@bot.message_handler(commands=['runningallcode'])
def command_run_all_code(message): _logic_run_all_scripts(message)
# 🆕
@bot.message_handler(commands=['hostingdashboard'])
def command_hosting_dashboard(message): _logic_hosting_dashboard(message)
@bot.message_handler(commands=['resourcemonitor'])
def command_resource_monitor(message): _logic_resource_monitor(message)
@bot.message_handler(commands=['backup'])
def command_backup(message): _logic_backup_all(message)
@bot.message_handler(commands=['autorestart'])
def command_autorestart(message): _logic_toggle_auto_restart(message)

@bot.message_handler(commands=['cancel'])
def command_cancel(message):
    user_id = message.from_user.id
    users_pending_folder.pop(user_id, None)
    users_awaiting_upload.discard(user_id)
    bot.reply_to(message, "❌ Action cancel ho gaya.\n\n👇 Niche se koi button press karo.",
                 reply_markup=create_reply_keyboard_main_menu(user_id))

@bot.message_handler(commands=['ping'])
def ping(message):
    start_ping_time = time.time()
    msg = bot.reply_to(message, "Pong!")
    latency = round((time.time() - start_ping_time) * 1000, 2)
    bot.edit_message_text(f"Pong! Latency: {latency} ms", message.chat.id, msg.message_id)

# ============================================================
# --- Ban/Unban ---
# ============================================================
def get_target_id(target):
    if target.isdigit():
        return int(target)
    try:
        chat = bot.get_chat(target.replace("@", ""))
        return chat.id
    except:
        return None

@bot.message_handler(commands=['ban'])
def command_ban_user(message):
    if message.from_user.id not in admin_ids and message.from_user.id != OWNER_ID:
        bot.reply_to(message, "⚠️ Not authorized."); return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Format: `/ban <ID/@Username> [reason]`"); return
    target_id = get_target_id(parts[1])
    if target_id is None:
        bot.reply_to(message, "⚠️ User nahi mila."); return
    if target_id == OWNER_ID or target_id in admin_ids:
        bot.reply_to(message, "⚠️ Admin/Owner ko ban nahi kar sakte."); return
    try:
        t = bot.get_chat(target_id)
        t_name, t_user = t.first_name, f"@{t.username}" if t.username else "No Username"
    except: t_name, t_user = "Unknown", "No Username"
    reason = parts[2].strip() if len(parts) > 2 else "No reason given"
    ban_user_db(target_id, reason, t_name, t_user)
    owner_msg = (f"🚫 *New Ban Alert*\n\n"
                 f"👮 *Admin:* {message.from_user.first_name} (@{message.from_user.username or 'N/A'}) ID: `{message.from_user.id}`\n"
                 f"👤 *Banned:* {t_name} ({t_user}) ID: `{target_id}`\n"
                 f"📝 *Reason:* {reason}")
    try: bot.send_message(OWNER_ID, owner_msg, parse_mode='Markdown')
    except: pass
    try: bot.send_message(target_id, f"🚫 Aapko ban kar diya gaya hai.\n📝 Reason: {reason}")
    except: pass
    bot.reply_to(message, f"✅ User `{target_id}` banned.", parse_mode='Markdown')

@bot.message_handler(commands=['unban'])
def command_unban_user(message):
    if message.from_user.id not in admin_ids and message.from_user.id != OWNER_ID:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Format: `/unban <ID/@Username>`"); return
    target_id = get_target_id(parts[1])
    if target_id and unban_user_db(target_id):
        bot.reply_to(message, f"✅ User `{target_id}` unbanned.", parse_mode='Markdown')
        try: bot.send_message(target_id, "✅ Aapko unban kar diya gaya hai.")
        except: pass
    else:
        bot.reply_to(message, "ℹ️ User banned list mein nahi mila.")

# ============================================================
# --- Document Handler ---
# ============================================================
@bot.message_handler(content_types=['document'])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    doc = message.document
    logger.info(f"Doc from {user_id}: {doc.file_name} ({doc.mime_type}), Size: {doc.file_size}")

    if user_id in banned_users:
        bot.reply_to(message, "🚫 You are banned."); return
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked, cannot accept files."); return

    if user_id not in users_awaiting_upload:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📤 Upload File", callback_data='upload'))
        bot.reply_to(message,
            "⚠️ Seedha file mat bhejo!\n\nPehle *Upload File* button pe click karo, folder name do, phir file bhejo. ✅",
            reply_markup=markup, parse_mode='Markdown')
        return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        users_awaiting_upload.discard(user_id)
        users_pending_folder.pop(user_id, None)
        bot.reply_to(message, f"⚠️ File limit ({current_files}/{limit_str}) reached. Delete files via /checkfiles.")
        return

    file_name = doc.file_name
    if not file_name:
        bot.reply_to(message, "⚠️ No file name."); return
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "⚠️ Unsupported! Only `.py`, `.js`, `.zip`."); return
    max_file_size = 20 * 1024 * 1024
    if doc.file_size > max_file_size:
        bot.reply_to(message, f"⚠️ Too large (Max {max_file_size // 1024 // 1024} MB)."); return

    try:
        try:
            bot.forward_message(OWNER_ID, chat_id, message.message_id)
            bot.send_message(OWNER_ID, f"⬆️ File '{file_name}' from {message.from_user.first_name} (`{user_id}`)", parse_mode='Markdown')
        except Exception as e: logger.error(f"Forward to owner failed: {e}")

        users_awaiting_upload.discard(user_id)
        folder_name = users_pending_folder.pop(user_id, None)

        download_wait_msg = bot.reply_to(message, f"⏳ Downloading `{file_name}`...")
        file_info_tg_doc = bot.get_file(doc.file_id)
        downloaded_file_content = bot.download_file(file_info_tg_doc.file_path)
        bot.edit_message_text(f"✅ Downloaded `{file_name}`. Processing...", chat_id, download_wait_msg.message_id)
        logger.info(f"Downloaded {file_name} for user {user_id}")

        base_user_folder = get_user_folder(user_id)
        if folder_name:
            user_folder = os.path.join(base_user_folder, folder_name)
            os.makedirs(user_folder, exist_ok=True)
        else:
            user_folder = base_user_folder

        if file_ext == '.zip':
            handle_zip_file(downloaded_file_content, file_name, message, user_folder)
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as f: f.write(downloaded_file_content)
            logger.info(f"Saved file: {file_path}")
            if file_ext == '.js': handle_js_file(file_path, user_id, user_folder, file_name, message)
            elif file_ext == '.py': handle_py_file(file_path, user_id, user_folder, file_name, message)
    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"TG API error: {e}", exc_info=True)
        if "file is too big" in str(e).lower():
            bot.reply_to(message, f"❌ Telegram API: File too large (~20MB limit).")
        else:
            bot.reply_to(message, f"❌ TG API: {str(e)}")
    except Exception as e:
        logger.error(f"❌ File error: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Unexpected: {str(e)}")

# ============================================================
# --- Callback Query Router ---
# ============================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    logger.info(f"Callback: User={user_id}, Data='{data}'")

    if user_id in banned_users:
        bot.answer_callback_query(call.id, "🚫 You are banned.", show_alert=True); return

    if bot_locked and user_id not in admin_ids and data not in ['back_to_main', 'speed', 'stats']:
        bot.answer_callback_query(call.id, "⚠️ Bot locked by admin.", show_alert=True)
        return
    try:
        if data == 'upload': upload_callback(call)
        elif data == 'check_files': check_files_callback(call)
        elif data.startswith('fold_'): folder_files_callback(call)
        elif data.startswith('file_'): file_control_callback(call)
        elif data.startswith('start_'): start_bot_callback(call)
        elif data.startswith('stop_'): stop_bot_callback(call)
        elif data.startswith('restart_'): restart_bot_callback(call)
        elif data.startswith('delete_'): delete_bot_callback(call)
        elif data.startswith('logs_'): logs_bot_callback(call)
        elif data.startswith('backup_file_'): backup_single_file_callback(call)  # 🆕
        elif data == 'speed': speed_callback(call)
        elif data == 'back_to_main': back_to_main_callback(call)
        elif data.startswith('confirm_broadcast_'): handle_confirm_broadcast(call)
        elif data == 'cancel_broadcast': handle_cancel_broadcast(call)
        # Admin callbacks
        elif data == 'subscription': admin_required_callback(call, subscription_management_callback)
        elif data == 'stats': stats_callback(call)
        elif data == 'lock_bot': admin_required_callback(call, lock_bot_callback)
        elif data == 'unlock_bot': admin_required_callback(call, unlock_bot_callback)
        elif data == 'run_all_scripts': admin_required_callback(call, run_all_scripts_callback)
        elif data == 'broadcast': admin_required_callback(call, broadcast_init_callback)
        elif data == 'admin_panel': admin_required_callback(call, admin_panel_callback)
        # 🆕 NEW
        elif data == 'hosting_dashboard': admin_required_callback(call, _logic_hosting_dashboard)
        elif data == 'resource_monitor': admin_required_callback(call, _logic_resource_monitor)
        elif data == 'backup_all': admin_required_callback(call, _logic_backup_all)
        elif data == 'toggle_auto_restart': admin_required_callback(call, _logic_toggle_auto_restart)
        # Admin mgmt
        elif data == 'add_admin': owner_required_callback(call, add_admin_init_callback)
        elif data == 'remove_admin': owner_required_callback(call, remove_admin_init_callback)
        elif data == 'list_admins': admin_required_callback(call, list_admins_callback)
        elif data == 'add_subscription': admin_required_callback(call, add_subscription_init_callback)
        elif data == 'remove_subscription': admin_required_callback(call, remove_subscription_init_callback)
        elif data == 'check_subscription': admin_required_callback(call, check_subscription_init_callback)
        elif data == 'edit_subscription': admin_required_callback(call, edit_subscription_init_callback)
        elif data == 'set_user_limit': admin_required_callback(call, set_user_limit_init_callback)
        elif data == 'list_premium': admin_required_callback(call, list_premium_users_callback)
        # Ban list callback
        elif data in ["ban_menu", "unban_menu", "ban_list"]:
            callback_admin(call)
        else:
            bot.answer_callback_query(call.id, "Unknown action.")
            logger.warning(f"Unhandled callback: {data}")
    except Exception as e:
        logger.error(f"Callback '{data}' error: {e}", exc_info=True)
        try: bot.answer_callback_query(call.id, "Error processing.", show_alert=True)
        except Exception as e_ans: logger.error(f"Answer callback fail: {e_ans}")

def admin_required_callback(call, func_to_run):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin permissions required.", show_alert=True); return
    func_to_run(call)

def owner_required_callback(call, func_to_run):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "⚠️ Owner permissions required.", show_alert=True); return
    func_to_run(call)

# ============================================================
# --- Callback Implementations ---
# ============================================================
def upload_callback(call):
    user_id = call.from_user.id
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.answer_callback_query(call.id, f"⚠️ File limit ({current_files}/{limit_str}) reached.", show_alert=True); return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📁 Pehle apni file ke liye ek *folder name* type karo:\n\n(Sirf letters, numbers, space, `-`, `_`, `.` allowed. Example: `my_bot`)\n\n/cancel - cancel", parse_mode='Markdown')
    bot.register_next_step_handler(msg, _process_folder_name_step)

def check_files_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    folders = _get_user_folder_names(user_id)
    if not folders:
        bot.answer_callback_query(call.id, "⚠️ Koi folders nahi hain.", show_alert=True)
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main'))
            bot.edit_message_text("📂 Koi folders nahi abhi.\n\n📤 Upload File se upload karo!", chat_id, call.message.message_id, reply_markup=markup)
        except Exception as e: logger.error(f"Empty folder msg: {e}")
        return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    for folder in folders:
        files_in = _get_files_in_folder(user_id, folder)
        running_count = sum(1 for fn, _ in files_in if is_bot_running(user_id, fn, folder))
        total = len(files_in)
        status_icon = "🟢" if running_count > 0 else "📁"
        btn_text = f"{status_icon} {folder}  ({running_count} running / {total} files)"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'fold_{user_id}_{folder}'))
    markup.add(types.InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main'))
    try:
        bot.edit_message_text("📂 Tumhare Folders:\nFolder pe click karo files dekhne ke liye.", chat_id, call.message.message_id, reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" in str(e): logger.warning("Msg not modified (folders).")
        else: logger.error(f"Edit folder list error: {e}")
    except Exception as e: logger.error(f"Unexpected folder list error: {e}", exc_info=True)

def folder_files_callback(call):
    try:
        _, user_id_str, folder_name = call.data.split('_', 2)
        user_id = int(user_id_str)
        requesting_user_id = call.from_user.id
        chat_id = call.message.chat.id

        if not (requesting_user_id == user_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Sirf apne folders manage kar sakte ho.", show_alert=True); return

        files_in = _get_files_in_folder(user_id, folder_name)
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=1)

        if not files_in:
            markup.add(types.InlineKeyboardButton("🔙 Back to Folders", callback_data='check_files'))
            try:
                bot.edit_message_text(f"📁 Folder: *{folder_name}*\n\nIs folder mein koi script file nahi hai.",
                    chat_id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
            except Exception as e: logger.error(f"Empty folder edit error: {e}")
            return

        for file_name, file_type in files_in:
            is_running = is_bot_running(user_id, file_name, folder_name)
            status_icon = "🟢 Running" if is_running else "🔴 Stopped"
            btn_text = f"{file_name} ({file_type}) - {status_icon}"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{folder_name}|{file_name}'))
        markup.add(types.InlineKeyboardButton("🔙 Back to Folders", callback_data='check_files'))

        try:
            bot.edit_message_text(f"📁 Folder: *{folder_name}*\n\nFiles — click to manage:",
                chat_id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" in str(e): logger.warning(f"Msg not modified (folder files)")
            else: logger.error(f"Edit folder files error: {e}")
        except Exception as e: logger.error(f"Unexpected folder files: {e}", exc_info=True)
    except (ValueError, IndexError) as ve:
        logger.error(f"Fold callback parse: {ve}. Data: '{call.data}'")
        bot.answer_callback_query(call.id, "Error: Invalid data.", show_alert=True)

def file_control_callback(call):
    try:
        _, script_owner_id_str, remainder = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        folder_name, file_name = remainder.split('|', 1)
        requesting_user_id = call.from_user.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ You can only manage your own files.", show_alert=True)
            check_files_callback(call); return

        base_folder = get_user_folder(script_owner_id)
        user_folder = os.path.join(base_folder, folder_name) if folder_name != '__root__' else base_folder
        file_path = os.path.join(user_folder, file_name)
        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, "⚠️ File not found on disk.", show_alert=True)
            check_files_callback(call); return

        bot.answer_callback_query(call.id)
        is_running = is_bot_running(script_owner_id, file_name, folder_name)
        status_text = '🟢 Running' if is_running else '🔴 Stopped'
        file_type = os.path.splitext(file_name)[1].lstrip('.')
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nFolder: `{folder_name}`\nStatus: {status_text}",
                call.message.chat.id, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_running, folder_name),
                parse_mode='Markdown')
        except telebot.apihelper.ApiTelegramException as e:
             if "message is not modified" in str(e): logger.warning(f"Msg not modified (controls)")
             else: raise
    except (ValueError, IndexError) as ve:
        logger.error(f"File control parse: {ve}. Data: '{call.data}'")
        bot.answer_callback_query(call.id, "Error: Invalid action data.", show_alert=True)
    except Exception as e:
        logger.error(f"File control error: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "An error occurred.", show_alert=True)

def start_bot_callback(call):
    try:
        _, script_owner_id_str, remainder = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        folder_name, file_name = remainder.split('|', 1)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return

        base_folder = get_user_folder(script_owner_id)
        user_folder = os.path.join(base_folder, folder_name) if folder_name != '__root__' else base_folder
        file_path = os.path.join(user_folder, file_name)
        file_type = os.path.splitext(file_name)[1].lstrip('.')

        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, f"⚠️ File `{file_name}` missing! Re-upload.", show_alert=True)
            check_files_callback(call); return

        if is_bot_running(script_owner_id, file_name, folder_name):
            bot.answer_callback_query(call.id, f"⚠️ '{file_name}' already running.", show_alert=True)
            try: bot.edit_message_reply_markup(chat_id_for_reply, call.message.message_id, reply_markup=create_control_buttons(script_owner_id, file_name, True, folder_name))
            except Exception as e: logger.error(f"Button update (already running): {e}")
            return

        bot.answer_callback_query(call.id, f"⏳ Starting {file_name}...")
        if file_type == 'py':
            threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        else:
            bot.send_message(chat_id_for_reply, f"❌ Unknown type '{file_type}'."); return

        time.sleep(1.5)
        is_now_running = is_bot_running(script_owner_id, file_name, folder_name)
        status_text = '🟢 Running' if is_now_running else '🟡 Starting (or failed, check logs)'
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nFolder: `{folder_name}`\nStatus: {status_text}",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_now_running, folder_name), parse_mode='Markdown')
        except telebot.apihelper.ApiTelegramException as e:
             if "message is not modified" in str(e): logger.warning(f"Msg not modified after start")
             else: raise
    except (ValueError, IndexError) as e:
        logger.error(f"Start parse: {e}"); bot.answer_callback_query(call.id, "Error: Invalid start.", show_alert=True)
    except Exception as e:
        logger.error(f"Start error: {e}", exc_info=True); bot.answer_callback_query(call.id, "Error starting.", show_alert=True)

def stop_bot_callback(call):
    try:
        _, script_owner_id_str, remainder = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        folder_name, file_name = remainder.split('|', 1)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return

        file_type = os.path.splitext(file_name)[1].lstrip('.')
        script_key = f"{script_owner_id}|{folder_name}|{file_name}"

        if not is_bot_running(script_owner_id, file_name, folder_name):
            bot.answer_callback_query(call.id, f"⚠️ '{file_name}' already stopped.", show_alert=True)
            try:
                bot.edit_message_text(
                    f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nFolder: `{folder_name}`\nStatus: 🔴 Stopped",
                    chat_id_for_reply, call.message.message_id,
                    reply_markup=create_control_buttons(script_owner_id, file_name, False, folder_name), parse_mode='Markdown')
            except Exception as e: logger.error(f"Button update: {e}")
            return

        bot.answer_callback_query(call.id, f"⏳ Stopping {file_name}...")
        process_info = bot_scripts.get(script_key)
        if process_info:
            kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]
        auto_restart_tracker.pop(script_key, None)

        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nFolder: `{folder_name}`\nStatus: 🔴 Stopped",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, False, folder_name), parse_mode='Markdown')
        except telebot.apihelper.ApiTelegramException as e:
             if "message is not modified" in str(e): logger.warning("Msg not modified after stop")
             else: raise
    except (ValueError, IndexError) as e:
        logger.error(f"Stop parse: {e}"); bot.answer_callback_query(call.id, "Error: Invalid stop.", show_alert=True)
    except Exception as e:
        logger.error(f"Stop error: {e}", exc_info=True); bot.answer_callback_query(call.id, "Error stopping.", show_alert=True)

def restart_bot_callback(call):
    try:
        _, script_owner_id_str, remainder = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        folder_name, file_name = remainder.split('|', 1)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return

        file_type = os.path.splitext(file_name)[1].lstrip('.')
        base_folder = get_user_folder(script_owner_id)
        user_folder = os.path.join(base_folder, folder_name) if folder_name != '__root__' else base_folder
        file_path = os.path.join(user_folder, file_name)
        script_key = f"{script_owner_id}|{folder_name}|{file_name}"

        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, f"⚠️ File `{file_name}` missing!", show_alert=True)
            if script_key in bot_scripts: del bot_scripts[script_key]
            check_files_callback(call); return

        bot.answer_callback_query(call.id, f"⏳ Restarting {file_name}...")
        if is_bot_running(script_owner_id, file_name, folder_name):
            process_info = bot_scripts.get(script_key)
            if process_info: kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]
            time.sleep(1.5)
        auto_restart_tracker.pop(script_key, None)

        if file_type == 'py':
            threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        else:
            bot.send_message(chat_id_for_reply, f"❌ Unknown type '{file_type}'."); return

        time.sleep(1.5)
        is_now_running = is_bot_running(script_owner_id, file_name, folder_name)
        status_text = '🟢 Running' if is_now_running else '🟡 Starting (or failed)'
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nFolder: `{folder_name}`\nStatus: {status_text}",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_now_running, folder_name), parse_mode='Markdown')
        except telebot.apihelper.ApiTelegramException as e:
             if "message is not modified" in str(e): logger.warning("Msg not modified (restart)")
             else: raise
    except (ValueError, IndexError) as e:
        logger.error(f"Restart parse: {e}"); bot.answer_callback_query(call.id, "Error: Invalid restart.", show_alert=True)
    except Exception as e:
        logger.error(f"Restart error: {e}", exc_info=True); bot.answer_callback_query(call.id, "Error restarting.", show_alert=True)

def delete_bot_callback(call):
    try:
        _, script_owner_id_str, remainder = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        folder_name, file_name = remainder.split('|', 1)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return

        bot.answer_callback_query(call.id, f"🗑️ Deleting {file_name}...")
        script_key = f"{script_owner_id}|{folder_name}|{file_name}"
        if is_bot_running(script_owner_id, file_name, folder_name):
            process_info = bot_scripts.get(script_key)
            if process_info: kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]
            time.sleep(0.5)
        auto_restart_tracker.pop(script_key, None)

        base_folder = get_user_folder(script_owner_id)
        user_folder = os.path.join(base_folder, folder_name) if folder_name != '__root__' else base_folder
        file_path = os.path.join(user_folder, file_name)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        if os.path.exists(file_path):
            try: os.remove(file_path); logger.info(f"Deleted: {file_path}")
            except OSError as e: logger.error(f"Error deleting {file_path}: {e}")
        if os.path.exists(log_path):
            try: os.remove(log_path); logger.info(f"Deleted log: {log_path}")
            except OSError as e: logger.error(f"Error deleting log {log_path}: {e}")

        remove_user_file_db(script_owner_id, file_name)

        folder_deleted = False
        if folder_name != '__root__' and os.path.isdir(user_folder):
            remaining = [f for f in os.listdir(user_folder)
                         if os.path.isfile(os.path.join(user_folder, f))
                         and os.path.splitext(f)[1].lower() in ('.py', '.js')]
            if not remaining:
                try:
                    shutil.rmtree(user_folder)
                    logger.info(f"Auto-deleted empty folder: {user_folder}")
                    folder_deleted = True
                except Exception as fe: logger.error(f"Folder delete error: {fe}")

        extra = f"\n📁 Folder `{folder_name}` bhi delete ho gaya (khaali tha)." if folder_deleted else ""
        try:
            bot.edit_message_text(f"🗑️ `{file_name}` deleted from `{folder_name}`!{extra}",
                chat_id_for_reply, call.message.message_id, reply_markup=None, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Delete edit msg error: {e}")
            bot.send_message(chat_id_for_reply, f"🗑️ `{file_name}` deleted.", parse_mode='Markdown')
    except (ValueError, IndexError) as e:
        logger.error(f"Delete parse: {e}"); bot.answer_callback_query(call.id, "Error: Invalid delete.", show_alert=True)
    except Exception as e:
        logger.error(f"Delete error: {e}", exc_info=True); bot.answer_callback_query(call.id, "Error deleting.", show_alert=True)

def logs_bot_callback(call):
    try:
        _, script_owner_id_str, remainder = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        folder_name, file_name = remainder.split('|', 1)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return

        base_folder = get_user_folder(script_owner_id)
        user_folder = os.path.join(base_folder, folder_name) if folder_name != '__root__' else base_folder
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        if not os.path.exists(log_path):
            bot.answer_callback_query(call.id, f"⚠️ No logs for '{file_name}'.", show_alert=True); return

        bot.answer_callback_query(call.id)
        try:
            log_content = ""; file_size = os.path.getsize(log_path)
            max_log_kb = 100; max_tg_msg = 4096
            if file_size == 0: log_content = "(Log empty)"
            elif file_size > max_log_kb * 1024:
                 with open(log_path, 'rb') as f:
                     f.seek(-max_log_kb * 1024, os.SEEK_END); log_bytes = f.read()
                 log_content = log_bytes.decode('utf-8', errors='ignore')
                 log_content = f"(Last {max_log_kb} KB)\n...\n" + log_content
            else:
                 with open(log_path, 'r', encoding='utf-8', errors='ignore') as f: log_content = f.read()

            if len(log_content) > max_tg_msg:
                log_content = log_content[-max_tg_msg:]
                first_nl = log_content.find('\n')
                if first_nl != -1: log_content = "...\n" + log_content[first_nl+1:]
                else: log_content = "...\n" + log_content
            if not log_content.strip(): log_content = "(No visible content)"

            bot.send_message(chat_id_for_reply,
                f"📜 Logs for `{file_name}` (User `{script_owner_id}`):\n```\n{log_content}\n```",
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Log read error {log_path}: {e}", exc_info=True)
            bot.send_message(chat_id_for_reply, f"❌ Error reading log `{file_name}`.")
    except (ValueError, IndexError) as e:
        logger.error(f"Logs parse: {e}"); bot.answer_callback_query(call.id, "Error: Invalid logs cmd.", show_alert=True)
    except Exception as e:
        logger.error(f"Logs error: {e}", exc_info=True); bot.answer_callback_query(call.id, "Error fetching logs.", show_alert=True)

def speed_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    start_cb_ping_time = time.time()
    try:
        bot.edit_message_text("🏃 Testing speed...", chat_id, call.message.message_id)
        bot.send_chat_action(chat_id, 'typing')
        response_time = round((time.time() - start_cb_ping_time) * 1000, 2)
        status = "🔓 Unlocked" if not bot_locked else "🔒 Locked"
        if user_id == OWNER_ID: user_level = "👑 Owner"
        elif user_id in admin_ids: user_level = "🛡️ Admin"
        elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now(): user_level = "⭐ Premium"
        else: user_level = "🆓 Free User"
        speed_msg = (f"⚡ Bot Speed & Status:\n\n⏱️ API Response Time: {response_time} ms\n"
                     f"🚦 Bot Status: {status}\n"
                     f"♻️ Auto-Restart: {'ON' if auto_restart_enabled else 'OFF'}\n"
                     f"👤 Your Level: {user_level}")
        bot.answer_callback_query(call.id)
        bot.edit_message_text(speed_msg, chat_id, call.message.message_id, reply_markup=create_main_menu_inline(user_id))
    except Exception as e:
         logger.error(f"Speed cb error: {e}", exc_info=True)
         bot.answer_callback_query(call.id, "Error in speed test.", show_alert=True)
         try: bot.edit_message_text("〽️ Main Menu", chat_id, call.message.message_id, reply_markup=create_main_menu_inline(user_id))
         except Exception: pass

def back_to_main_callback(call):
    chat_id = call.message.chat.id
    try:
        bot.answer_callback_query(call.id)
        bot.delete_message(chat_id, call.message.message_id)
    except telebot.apihelper.ApiTelegramException as e:
        if "message to delete not found" in str(e) or "message can't be deleted" in str(e):
            try: bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
            except Exception: pass
        else:
            logger.error(f"API error back_to_main: {e}")
    except Exception as e:
        logger.error(f"back_to_main error: {e}", exc_info=True)

# 🆕 Single file backup callback
def backup_single_file_callback(call):
    try:
        _, uid_str, rem = call.data.split('_', 2)
        target_uid = int(uid_str)
        folder, fname = rem.split('|', 1)
        req_uid = call.from_user.id
        if not (req_uid == target_uid or req_uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Denied.", show_alert=True); return
        base = get_user_folder(target_uid)
        uf = os.path.join(base, folder) if folder != '__root__' else base
        fp = os.path.join(uf, fname)
        if not os.path.exists(fp):
            bot.answer_callback_query(call.id, "⚠️ File missing.", show_alert=True); return
        bot.answer_callback_query(call.id, "💾 Creating backup...")
        bpath = create_single_file_backup(target_uid, folder, fname)
        if bpath and os.path.exists(bpath):
            size_kb = os.path.getsize(bpath) // 1024
            with open(bpath, 'rb') as f:
                bot.send_document(call.message.chat.id, f,
                                  caption=f"💾 Backup of `{fname}`\nUser: `{target_uid}`\nSize: {size_kb} KB",
                                  parse_mode='Markdown')
        else:
            bot.send_message(call.message.chat.id, "❌ Backup failed.")
    except Exception as e:
        logger.error(f"Single backup error: {e}", exc_info=True)
        try: bot.send_message(call.message.chat.id, f"❌ Error: {e}")
        except: pass

# ============================================================
# --- Admin Callback Implementations ---
# ============================================================
def subscription_management_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("💳 Subscription Management\nSelect action:",
            call.message.chat.id, call.message.message_id, reply_markup=create_subscription_menu())
    except Exception as e: logger.error(f"Sub menu error: {e}")

def stats_callback(call):
    bot.answer_callback_query(call.id)
    _logic_statistics(call.message)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                      reply_markup=create_main_menu_inline(call.from_user.id))
    except Exception as e:
        logger.error(f"Menu update after stats: {e}")

def lock_bot_callback(call):
    global bot_locked; bot_locked = True
    logger.warning(f"Bot locked by Admin {call.from_user.id}")
    bot.answer_callback_query(call.id, "🔒 Bot locked.")
    try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(call.from_user.id))
    except Exception as e: logger.error(f"Menu update (lock): {e}")

def unlock_bot_callback(call):
    global bot_locked; bot_locked = False
    logger.warning(f"Bot unlocked by Admin {call.from_user.id}")
    bot.answer_callback_query(call.id, "🔓 Bot unlocked.")
    try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(call.from_user.id))
    except Exception as e: logger.error(f"Menu update (unlock): {e}")

def run_all_scripts_callback(call):
    _logic_run_all_scripts(call)

def broadcast_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📢 Send message to broadcast.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def process_broadcast_message(message):
    user_id = message.from_user.id
    if user_id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text and message.text.lower() == '/cancel': bot.reply_to(message, "Broadcast cancelled."); return

    broadcast_content = message.text
    if not broadcast_content and not (message.photo or message.video or message.document or message.sticker or message.voice or message.audio):
         bot.reply_to(message, "⚠️ Cannot broadcast empty. /cancel")
         msg = bot.send_message(message.chat.id, "📢 Send broadcast or /cancel.")
         bot.register_next_step_handler(msg, process_broadcast_message)
         return

    target_count = len(active_users)
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("✅ Confirm & Send", callback_data=f"confirm_broadcast_{message.message_id}"),
               types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast"))

    preview_text = broadcast_content[:1000].strip() if broadcast_content else "(Media message)"
    bot.reply_to(message, f"⚠️ Confirm Broadcast:\n\n```\n{preview_text}\n```\n\nTo **{target_count}** users. Sure?",
                 reply_markup=markup, parse_mode='Markdown')

def handle_confirm_broadcast(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if user_id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True); return
    try:
        original_message = call.message.reply_to_message
        if not original_message: raise ValueError("Could not retrieve original message.")

        broadcast_text = None; broadcast_photo_id = None; broadcast_video_id = None
        if original_message.text: broadcast_text = original_message.text
        elif original_message.photo: broadcast_photo_id = original_message.photo[-1].file_id
        elif original_message.video: broadcast_video_id = original_message.video.file_id
        else: raise ValueError("No text or supported media.")

        bot.answer_callback_query(call.id, "🚀 Starting broadcast...")
        bot.edit_message_text(f"📢 Broadcasting to {len(active_users)} users...",
                              chat_id, call.message.message_id, reply_markup=None)
        thread = threading.Thread(target=execute_broadcast, args=(
            broadcast_text, broadcast_photo_id, broadcast_video_id,
            original_message.caption if (broadcast_photo_id or broadcast_video_id) else None,
            chat_id))
        thread.start()
    except ValueError as ve:
        logger.error(f"Broadcast confirm ValueError: {ve}")
        bot.edit_message_text(f"❌ Error: {ve}", chat_id, call.message.message_id, reply_markup=None)
    except Exception as e:
        logger.error(f"Confirm broadcast error: {e}", exc_info=True)
        bot.edit_message_text("❌ Unexpected error.", chat_id, call.message.message_id, reply_markup=None)

def handle_cancel_broadcast(call):
    bot.answer_callback_query(call.id, "Broadcast cancelled.")
    bot.delete_message(call.message.chat.id, call.message.message_id)
    if call.message.reply_to_message:
        try: bot.delete_message(call.message.chat.id, call.message.reply_to_message.message_id)
        except: pass

def execute_broadcast(broadcast_text, photo_id, video_id, caption, admin_chat_id):
    sent_count = 0; failed_count = 0; blocked_count = 0
    start_exec_time = time.time()
    users_to_broadcast = list(active_users); total_users = len(users_to_broadcast)
    logger.info(f"Broadcast exec to {total_users} users.")
    batch_size = 25; delay_batches = 1.5

    for i, user_id_bc in enumerate(users_to_broadcast):
        try:
            if broadcast_text: bot.send_message(user_id_bc, broadcast_text, parse_mode='Markdown')
            elif photo_id: bot.send_photo(user_id_bc, photo_id, caption=caption, parse_mode='Markdown' if caption else None)
            elif video_id: bot.send_video(user_id_bc, video_id, caption=caption, parse_mode='Markdown' if caption else None)
            sent_count += 1
        except telebot.apihelper.ApiTelegramException as e:
            err_desc = str(e).lower()
            if any(s in err_desc for s in ["bot was blocked", "user is deactivated", "chat not found", "kicked from", "restricted"]):
                blocked_count += 1
            elif "flood control" in err_desc or "too many requests" in err_desc:
                retry_after = 5; match = re.search(r"retry after (\d+)", err_desc)
                if match: retry_after = int(match.group(1)) + 1
                logger.warning(f"Flood control. Sleeping {retry_after}s...")
                time.sleep(retry_after)
                try:
                    if broadcast_text: bot.send_message(user_id_bc, broadcast_text, parse_mode='Markdown')
                    elif photo_id: bot.send_photo(user_id_bc, photo_id, caption=caption)
                    elif video_id: bot.send_video(user_id_bc, video_id, caption=caption)
                    sent_count += 1
                except Exception as e_retry: logger.error(f"Retry fail {user_id_bc}: {e_retry}"); failed_count += 1
            else: logger.error(f"Broadcast fail {user_id_bc}: {e}"); failed_count += 1
        except Exception as e:
            logger.error(f"Broadcast unexpected {user_id_bc}: {e}"); failed_count += 1

        if (i + 1) % batch_size == 0 and i < total_users - 1:
            logger.info(f"Batch {i//batch_size + 1} done. Sleeping...")
            time.sleep(delay_batches)
        elif i % 5 == 0: time.sleep(0.2)

    duration = round(time.time() - start_exec_time, 2)
    result_msg = (f"📢 Broadcast Complete!\n\n✅ Sent: {sent_count}\n❌ Failed: {failed_count}\n"
                  f"🚫 Blocked/Inactive: {blocked_count}\n👥 Targets: {total_users}\n⏱️ Duration: {duration}s")
    logger.info(result_msg)
    try: bot.send_message(admin_chat_id, result_msg)
    except Exception as e: logger.error(f"Broadcast result send fail: {e}")

def admin_panel_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("👑 Admin Panel\nManage admins.",
            call.message.chat.id, call.message.message_id, reply_markup=create_admin_panel())
    except Exception as e: logger.error(f"Admin panel error: {e}")

# Admin management callbacks
def add_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "👑 Enter User ID to promote to Admin.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_add_admin_id)

def process_add_admin_id(message):
    if message.from_user.id != OWNER_ID: bot.reply_to(message, "⚠️ Owner only."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelled."); return
    try:
        new_id = int(message.text.strip())
        add_admin_db(new_id)
        bot.reply_to(message, f"✅ Admin `{new_id}` added.", parse_mode='Markdown')
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID. Try again or /cancel.")
        msg = bot.send_message(message.chat.id, "Try again or /cancel.")
        bot.register_next_step_handler(msg, process_add_admin_id)

def remove_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "➖ Admin ID to remove. /cancel")
    bot.register_next_step_handler(msg, process_remove_admin_id)

def process_remove_admin_id(message):
    if message.from_user.id != OWNER_ID: bot.reply_to(message, "⚠️ Owner only."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelled."); return
    try:
        rid = int(message.text.strip())
        if remove_admin_db(rid): bot.reply_to(message, f"✅ Removed `{rid}`.", parse_mode='Markdown')
        else: bot.reply_to(message, "⚠️ Not an admin.")
    except ValueError: bot.reply_to(message, "⚠️ Invalid.")

def list_admins_callback(call):
    bot.answer_callback_query(call.id)
    lines = ["👑 *Admins:*"]
    for aid in admin_ids:
        if aid == OWNER_ID: lines.append(f"👑 `{aid}` (Owner)")
        else: lines.append(f"🛡️ `{aid}`")
    try: bot.send_message(call.message.chat.id, "\n".join(lines), parse_mode='Markdown')
    except Exception as e: logger.error(f"List admins error: {e}")

def add_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Format: `<user_id> <days> [file_limit]`\nExample: `123456 30 10`\n/cancel")
    bot.register_next_step_handler(msg, process_add_subscription)

def process_add_subscription(message):
    if message.from_user.id not in admin_ids: bot.reply_to(message, "⚠️ Admin only."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelled."); return
    parts = message.text.split()
    if len(parts) < 2: bot.reply_to(message, "⚠️ Invalid format."); return
    try:
        uid = int(parts[0]); days = int(parts[1]); limit = int(parts[2]) if len(parts) > 2 else None
        expiry = datetime.now() + timedelta(days=days)
        save_subscription(uid, expiry, limit)
        bot.reply_to(message, f"✅ Sub for `{uid}` — {days}d, limit: {limit or 'default'}", parse_mode='Markdown')
    except ValueError: bot.reply_to(message, "⚠️ Invalid input.")

def remove_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 User ID to remove sub. /cancel")
    bot.register_next_step_handler(msg, process_remove_subscription)

def process_remove_subscription(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelled."); return
    try:
        uid = int(message.text.strip())
        remove_subscription_db(uid)
        bot.reply_to(message, f"✅ Removed sub for `{uid}`.", parse_mode='Markdown')
    except ValueError: bot.reply_to(message, "⚠️ Invalid.")

def check_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 User ID to check. /cancel")
    bot.register_next_step_handler(msg, process_check_subscription)

def process_check_subscription(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        uid = int(message.text.strip())
        if uid in user_subscriptions:
            sub = user_subscriptions[uid]
            days = (sub['expiry'] - datetime.now()).days
            bot.reply_to(message, f"⭐ `{uid}`\nExpiry: {sub['expiry'].strftime('%Y-%m-%d')}\nDays left: {days}\nLimit: {sub.get('file_limit') or 'default'}", parse_mode='Markdown')
        elif uid in user_custom_limits:
            bot.reply_to(message, f"🎯 `{uid}` custom limit: {user_custom_limits[uid]}", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"🆓 `{uid}` has no sub.", parse_mode='Markdown')
    except ValueError: bot.reply_to(message, "⚠️ Invalid.")

def edit_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "✏️ Format: `<user_id> <new_days> [new_limit]`\n/cancel")
    bot.register_next_step_handler(msg, process_edit_subscription)

def process_edit_subscription(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    parts = message.text.split()
    if len(parts) < 2: bot.reply_to(message, "⚠️ Invalid."); return
    try:
        uid = int(parts[0]); days = int(parts[1]); limit = int(parts[2]) if len(parts) > 2 else None
        expiry = datetime.now() + timedelta(days=days)
        save_subscription(uid, expiry, limit)
        bot.reply_to(message, f"✅ Sub updated for `{uid}` — {days}d", parse_mode='Markdown')
    except ValueError: bot.reply_to(message, "⚠️ Invalid.")

def set_user_limit_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔢 Format: `<user_id> <file_limit>`\n/cancel")
    bot.register_next_step_handler(msg, process_set_user_limit)

def process_set_user_limit(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    parts = message.text.split()
    if len(parts) != 2: bot.reply_to(message, "⚠️ Invalid."); return
    try:
        uid = int(parts[0]); lim = int(parts[1])
        save_user_custom_limit(uid, lim)
        bot.reply_to(message, f"✅ Custom limit `{lim}` for `{uid}`.", parse_mode='Markdown')
    except ValueError: bot.reply_to(message, "⚠️ Invalid.")

def list_premium_users_callback(call):
    bot.answer_callback_query(call.id)
    if not user_subscriptions:
        bot.send_message(call.message.chat.id, "No premium users."); return
    lines = ["⭐ *Premium Users:*"]
    for uid, sub in user_subscriptions.items():
        days = (sub['expiry'] - datetime.now()).days
        if days >= 0:
            lines.append(f"`{uid}` — {days}d left — limit: {sub.get('file_limit') or 'default'}")
    try: bot.send_message(call.message.chat.id, "\n".join(lines), parse_mode='Markdown')
    except Exception as e: logger.error(f"List premium error: {e}")

# Ban list callback (original)
def callback_admin(call):
    if call.data == "ban_menu":
        bot.send_message(call.message.chat.id, "Type करें: `/ban <ID/@Username> [reason]`", parse_mode='Markdown')
    elif call.data == "unban_menu":
        bot.send_message(call.message.chat.id, "Type करें: `/unban <ID/@Username>`", parse_mode='Markdown')
    elif call.data == "ban_list":
        if not banned_users:
            bot.answer_callback_query(call.id, "Koi bhi user banned nahi hai."); return
        lines = ["🚫 *Banned Users List:*"]
        for uid, data in banned_users.items():
            name = data.get('name', 'Unknown')
            username = data.get('username', 'No Username')
            lines.append(f"👤 {name} ({username}) | ID: `{uid}`")
        bot.send_message(call.message.chat.id, "\n".join(lines), parse_mode='Markdown')

# ============================================================
# 🌐 WEBHOOK SETUP (Render)
# ============================================================
WEBHOOK_PATH = f"/webhook/{TOKEN}"

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook_receive():
    try:
        if request.headers.get('content-type') == 'application/json':
            update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
            bot.process_new_updates([update])
            return 'ok', 200
        return 'bad request', 400
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return 'error', 500

def setup_webhook():
    if not USE_WEBHOOK:
        logger.info("🔄 Webhook DISABLED — polling mode")
        return False
    if not WEBHOOK_URL:
        logger.warning("⚠️ WEBHOOK_URL not set. Falling back to polling.")
        return False
    try:
        bot.remove_webhook()
        time.sleep(1)
        full_url = WEBHOOK_URL + WEBHOOK_PATH
        bot.set_webhook(url=full_url)
        logger.info(f"🌐 Webhook set: {full_url}")
        return True
    except Exception as e:
        logger.error(f"Webhook setup failed: {e}")
        return False

# ============================================================
# 🚀 STARTUP
# ============================================================
if __name__ == '__main__':
    logger.info("🚀 Starting AYUSH HOSTER BOT...")
    logger.info(f"   Mode: {'WEBHOOK' if USE_WEBHOOK else 'POLLING'}")
    logger.info(f"   Port: {PORT}")

    # 🆕 Start auto-restart monitor thread
    threading.Thread(target=monitor_crashed_scripts, daemon=True).start()
    logger.info("♻️ Auto-restart monitor started")

    # Start Flask (for /health + webhook)
    keep_alive()

    if USE_WEBHOOK and setup_webhook():
        logger.info("🌐 Running in WEBHOOK mode")
        while True:
            time.sleep(3600)
    else:
        logger.info("📡 Running in POLLING mode")
        while True:
            try:
                bot.infinity_polling(timeout=30, long_polling_timeout=25)
            except Exception as e:
                logger.error(f"Polling crashed: {e}. Restarting in 5s...")
                time.sleep(5)