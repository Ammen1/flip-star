#!/bin/bash


# Flipstar Setup Script for Ethiopia Telecom Server
# This script performs initial setup for the server

set -e

echo "=== Flipstar Initial Setup Script ==="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "Docker installed. Please log out and log back in."
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Docker Compose is not installed. Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Create environment file
if [ ! -f .env ]; then
    echo "Creating .env file from example..."
    cp env.production.example .env
    echo "Please edit .env file with your configuration before deploying."
    echo "IMPORTANT: Update SECRET_KEY, DB_PASSWORD, AWS credentials, etc."
fi

# Create necessary directories
echo "Creating directories..."
mkdir -p backend/media
mkdir -p backend/staticfiles

# Set permissions
echo "Setting permissions..."
chmod +x deploy.sh
chmod +x backup.sh

echo "=== Setup Complete ==="
echo "Next steps:"
echo "1. Edit .env file with your configuration"
echo "2. Run ./deploy.sh to deploy the application"
