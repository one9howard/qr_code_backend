#!/bin/bash

# Configuration
TARGET_DIR="/opt/qr_code_backend1"
REPO_URL="https://github.com/one9howard/qr_code_backend.git"

print_msg() {
    echo -e "\033[1;32m$1\033[0m"
}

print_msg "Starting deployment of $REPO_URL to $TARGET_DIR..."

# 1. Update package list and install git if not present
if ! command -v git &> /dev/null; then
    print_msg "Git not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y git
fi

# 2. Clone the repository
if [ -d "$TARGET_DIR" ]; then
    echo "Directory $TARGET_DIR already exists."
    read -p "Do you want to delete it and re-clone? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_msg "Removing existing directory..."
        sudo rm -rf "$TARGET_DIR"
        print_msg "Cloning repository..."
        sudo git clone "$REPO_URL" "$TARGET_DIR"
    else
        print_msg "Skipping clone. Attempting git pull..."
        cd "$TARGET_DIR" || exit
        sudo git pull origin main
    fi
else
    print_msg "Cloning repository..."
    sudo git clone "$REPO_URL" "$TARGET_DIR"
fi

# 3. Create virtual environment and install dependencies (Optional but recommended)
read -p "Do you want to set up the python environment? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Install python3-venv if missing
    sudo apt-get install -y python3-venv python3-pip

    cd "$TARGET_DIR" || exit
    
    # Create venv if it doesn't exist
    if [ ! -d "venv" ]; then
        print_msg "Creating virtual environment..."
        python3 -m venv venv
    fi

    # Install requirements
    if [ -f "requirements.txt" ]; then
        print_msg "Installing requirements..."
        ./venv/bin/pip install -r requirements.txt
    fi
fi

# 4. Fix permissions (gives ownership to the current user)
if [ -d "$TARGET_DIR" ]; then
    print_msg "Changing ownership of $TARGET_DIR to $USER..."
    sudo chown -R "$USER":"$USER" "$TARGET_DIR"
fi

print_msg "Done! Code is deployed at $TARGET_DIR"
