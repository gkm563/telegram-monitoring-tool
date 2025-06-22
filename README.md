# Telegram-Controlled Monitoring Tool (Python)

This tool lets you remotely monitor and control your system using Telegram.  
Built by **Gautam Kumar Maurya (GKM)** using Python and the Telegram Bot API.

---

## Features

-  Sends "Bot is Ready" message on startup
-  Capture & send screenshots
-  Capture webcam image
-  System Info (RAM, CPU, Uptime)
-  Clipboard capture
-  Network Info
-  File list / disk usage
-  Continuous monitoring (looped)
-  Stop & Self-delete options
-  Controlled entirely via Telegram buttons

---

## Requirements

- Python 3.x
- Libraries:
```bash
pip install pyTelegramBotAPI psutil pyautogui opencv-python
