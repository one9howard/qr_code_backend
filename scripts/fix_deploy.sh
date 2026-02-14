#!/bin/bash
# Emergency fix script to update repo URL to HTTPS and fix permissions

TARGET_DIR="/opt/qr_code_backend"
USER_NAME=$(whoami)

echo "Fixing git remote URL..."
cd "$TARGET_DIR" || exit
# Force switch to HTTPS
sudo git remote set-url origin https://github.com/one9howard/qr_code_backend.git

echo "Pulling latest code..."
sudo git pull origin main

echo "Fixing service user to '$USER_NAME'..."
# Replace 'User=ubuntu' with actual user in service files
sudo sed -i "s/User=ubuntu/User=$USER_NAME/g" systemd/insite.service

echo "Fixing backend directory ownership..."
sudo chown -R "$USER_NAME:$USER_NAME" "$TARGET_DIR"

echo "Reloading and restarting services..."
sudo ln -sf "$TARGET_DIR/systemd/insite.service" /etc/systemd/system/insite.service
sudo systemctl daemon-reload
sudo systemctl restart insite

echo "Done! check status with: sudo systemctl status insite"
