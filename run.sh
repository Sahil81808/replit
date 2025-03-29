#!/bin/bash

echo "Installing requirements..."
pip install -q python-telegram-bot==20.3 Flask

echo "Starting bot in background using screen..."
screen -dmS advbot python3 gc.py

echo "Bot started in screen session named 'advbot'."
echo "Use 'screen -r advbot' to view logs."
