#!/bin/bash

echo "🚀 Setting up PayVerify on new machine..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    echo "Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    echo "Visit: https://docs.docker.com/compose/install/"
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp env.template .env
    echo "✅ .env file created. Please edit it with your server IP address."
    echo "   Current ALLOWED_HOSTS: localhost,127.0.0.1,0.0.0.0,YOUR_SERVER_IP"
    echo "   Replace YOUR_SERVER_IP with your actual server IP address."
    echo ""
    echo "Press Enter to continue after editing .env file..."
    read
fi

# Make scripts executable
chmod +x deploy.sh
chmod +x entrypoint.sh

echo "🐳 Starting Docker containers..."
./deploy.sh

echo "✅ Setup complete!"
echo "🌐 Your app should be running at: http://localhost"
echo "🔧 Admin panel: http://localhost/admin (admin/admin123)"
