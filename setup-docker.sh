#!/bin/bash
set -e

echo ESPN4CC4C Docker Setup
echo

# Check directory
if [ ! -f requirements.txt ] || [ ! -d bin ]; then
    echo ERROR: Run this from the ESPN4CC4C root folder
    exit 1
fi

echo Found ESPN4CC4C project files

# Get LAN IP
LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$LAN_IP" ]; then
    LAN_IP=$(ip addr show 2>/dev/null | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | cut -d/ -f1 | head -n1)
fi
if [ -z "$LAN_IP" ]; then
    LAN_IP=192.168.1.50
fi

echo Using LAN IP: $LAN_IP
echo

# Rest of the script follows...
