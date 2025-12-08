# MCP Server for IBM MQ - RHEL9 Installation Guide

Complete guide to install and run the MCP (Model Context Protocol) Server for IBM MQ monitoring on Red Hat Enterprise Linux 9.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Server](#running-the-server)
- [Testing](#testing)
- [Production Deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

- Red Hat Enterprise Linux 9 (RHEL9)
- Python 3.11 or higher
- Node.js 18.x or higher
- Active IBM MQ instance
- Running FastAPI MQ monitoring application

### Check Existing Installation

```bash
# Check OS version
cat /etc/redhat-release

# Check Python version
python3 --version

# Check Node. js version
node --version
npm --version
```

---

## Installation

### Step 1: Install Python 3.11+

RHEL9 includes Python 3.9 by default. Install Python 3.11:

```bash
# Check available Python versions
sudo dnf module list python3

# Install Python 3.11
sudo dnf module install python3.11 -y

# Install Python development packages
sudo dnf install python3. 11-pip python3.11-devel -y

# Verify installation
python3. 11 --version
```

**Expected output:** `Python 3.11.x`

---

### Step 2: Install Node.js and npm

#### Option A: Install from NodeSource (Recommended)

```bash
# Download and install Node.js 20.x LTS
curl -fsSL https://rpm. nodesource.com/setup_20.x | sudo bash -
sudo dnf install nodejs -y

# Verify installation
node --version
npm --version
```

#### Option B: Install from RHEL AppStream

```bash
# Check available versions
sudo dnf module list nodejs

# Install Node.js 18 (or latest available)
sudo dnf module install nodejs:18 -y

# Verify
node --version
npm --version
```

---

### Step 3: Install Development Tools

```bash
# Install development tools
sudo dnf groupinstall "Development Tools" -y

# Install additional dependencies
sudo dnf install gcc openssl-devel bzip2-devel libffi-devel -y
```

---

### Step 4: Create Project Directory

```bash
# Create project directory
mkdir -p ~/mq-mcp-server
cd ~/mq-mcp-server
```

---

### Step 5: Create Python Virtual Environment

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

**Note:** You should see `(venv)` in your terminal prompt. 

---

### Step 6: Install Python Dependencies

Create `requirements.txt`:

```bash
cat > requirements.txt << 'EOF'
# MCP Server Dependencies
mcp>=0.9.0
httpx>=0.27.0
python-dotenv>=1.0.0

# Optional: For development and testing
pytest>=8.0.0
pytest-asyncio>=0.23.0
EOF
```

Install dependencies:

```bash
pip install -r requirements. txt
```

Verify installation:

```bash
pip list | grep -E "mcp|httpx|python-dotenv"
```

---

### Step 7: Create Project Files

#### 1. Create `. env` file

```bash
cat > .env << 'EOF'
# MQ FastAPI Backend Configuration
MQ_API_BASE_URL=http://localhost:8000
MQ_API_USERNAME=admin
MQ_API_PASSWORD=Password123
MQ_QMGR_NAME=SRVIG

# Optional: Logging level
LOG_LEVEL=INFO
EOF
```

**🔧 IMPORTANT:** Update these values to match your environment:
- `MQ_API_BASE_URL` - Your FastAPI server URL
- `MQ_API_USERNAME` - Your FastAPI username
- `MQ_API_PASSWORD` - Your FastAPI password
- `MQ_QMGR_NAME` - Your queue manager name

Secure the file:

```bash
chmod 600 .env
```

#### 2. Create `mcp_mq_server.py`

Copy the complete MCP server code into this file:

```bash
nano mcp_mq_server. py
```

Paste the complete code, then save with `Ctrl+X`, `Y`, `Enter`.

#### 3. Create `. gitignore`

```bash
cat > .gitignore << 'EOF'
# Virtual Environment
venv/
env/
ENV/

# Python
__pycache__/
*. py[cod]
*$py.class
*.so
. Python

# Environment variables
.env
.env. local

# Logs
*.log
mcp_server_debug.log

# OS
.DS_Store
EOF
```

---

## Configuration

### Environment Variables

The MCP server uses these environment variables (set in `.env` file):

| Variable | Description | Example |
|----------|-------------|---------|
| `MQ_API_BASE_URL` | FastAPI server URL | `http://localhost:8000` |
| `MQ_API_USERNAME` | FastAPI username | `admin` |
| `MQ_API_PASSWORD` | FastAPI password | `Password123` |
| `MQ_QMGR_NAME` | Default queue manager name | `SRVIG` |
| `LOG_LEVEL` | Logging level | `INFO` or `DEBUG` |

### FastAPI Endpoints

The MCP server expects these endpoints from your FastAPI application:

- `POST /token` - Authentication endpoint
- `GET /qmgr/{qmgr_name}/status` - Queue manager status
- `GET /qmgr/{qmgr_name}/queues` - List all queues
- `GET /qmgr/{qmgr_name}/queues/{queue_name}` - Specific queue details
- `GET /qmgr/{qmgr_name}/channels` - List all channels
- `GET /qmgr/{qmgr_name}/channels/{channel_name}` - Specific channel details

---

## Running the Server

### Method 1: Interactive Mode (For Testing)

Create startup script:

```bash
cat > start_inspector.sh << 'EOF'
#!/bin/bash

echo "========================================"
echo "Starting MCP Inspector for MQ"
echo "========================================"
echo

# Change to script directory
cd "$(dirname "$0")"

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "Environment variables loaded from .env"
fi

echo "Configuration:"
echo "  Base URL: $MQ_API_BASE_URL"
echo "  Username: $MQ_API_USERNAME"
echo "  Queue Manager: $MQ_QMGR_NAME"
echo

# Check if FastAPI is accessible
echo "Checking FastAPI server..."
if curl -s --connect-timeout 3 "$MQ_API_BASE_URL/docs" > /dev/null 2>&1; then
    echo "  ✓ FastAPI is running"
else
    echo "  ✗ WARNING: Cannot reach FastAPI at $MQ_API_BASE_URL"
    echo "  Make sure your FastAPI server is running!"
fi

echo
echo "Starting MCP Inspector..."
echo "Access at: http://localhost:5173"
echo "Or from remote: http://$(hostname -I | awk '{print $1}'):5173"
echo "Press Ctrl+C to stop"
echo

# Start inspector
npx @modelcontextprotocol/inspector python mcp_mq_server.py
EOF

chmod +x start_inspector.sh
```

Run the server:

```bash
./start_inspector.sh
```

Access the web interface:
- **Locally:** `http://localhost:5173`
- **Remotely:** `http://your-server-ip:5173`

---

### Method 2: Using Screen (Background Process)

Install screen:

```bash
sudo dnf install screen -y
```

Start in screen session:

```bash
# Create new screen session
screen -S mcp-inspector

# Navigate to project
cd ~/mq-mcp-server

# Run the server
./start_inspector.sh

# Detach from screen: Press Ctrl+A, then D
```

Manage screen sessions:

```bash
# List all screen sessions
screen -ls

# Reattach to session
screen -r mcp-inspector

# Kill a session
screen -X -S mcp-inspector quit
```

---

### Method 3: Using tmux (Background Process)

Install tmux:

```bash
sudo dnf install tmux -y
```

Start in tmux session:

```bash
# Create new tmux session
tmux new -s mcp-inspector

# Navigate to project
cd ~/mq-mcp-server

# Run the server
./start_inspector.sh

# Detach from tmux: Press Ctrl+B, then D
```

Manage tmux sessions:

```bash
# List all tmux sessions
tmux ls

# Reattach to session
tmux attach -t mcp-inspector

# Kill a session
tmux kill-session -t mcp-inspector
```

---

### Method 4: systemd Service (Production)

Create systemd service file:

```bash
sudo nano /etc/systemd/system/mcp-mq-inspector.service
```

Paste this content (**replace `your_username` with your actual username**):

```ini
[Unit]
Description=MCP MQ Inspector Service
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/home/your_username/mq-mcp-server
Environment="MQ_API_BASE_URL=http://localhost:8000"
Environment="MQ_API_USERNAME=admin"
Environment="MQ_API_PASSWORD=Password123"
Environment="MQ_QMGR_NAME=SRVIG"
Environment="PATH=/home/your_username/mq-mcp-server/venv/bin:/usr/local/bin:/usr/bin:/bin"

ExecStart=/home/your_username/mq-mcp-server/venv/bin/python /home/your_username/mq-mcp-server/mcp_mq_server.py

Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Manage the service:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable mcp-mq-inspector

# Start service
sudo systemctl start mcp-mq-inspector

# Check status
sudo systemctl status mcp-mq-inspector

# Stop service
sudo systemctl stop mcp-mq-inspector

# Restart service
sudo systemctl restart mcp-mq-inspector

# View logs
sudo journalctl -u mcp-mq-inspector -f

# View last 100 lines
sudo journalctl -u mcp-mq-inspector -n 100
```

---

## Testing

### Test 1: Verify FastAPI Connection

```bash
# Test FastAPI docs endpoint
curl http://localhost:8000/docs

# Expected: HTML response or redirect
```

### Test 2: Test Authentication

```bash
# Test token endpoint
curl -X POST "http://localhost:8000/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Password123"

# Expected: JSON with access_token
```

### Test 3: Test MCP Server Directly

Create test script:

```bash
cat > test_mcp_direct.py << 'EOF'
"""Direct test of MCP server"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from mcp_mq_server import TokenManager, MQApiClient, MCPConfig

async def test():
    print("=" * 60)
    print("Direct MCP Server Test")
    print("=" * 60)
    
    print(f"\nConfiguration:")
    print(f"  Base URL: {MCPConfig. FASTAPI_BASE_URL}")
    print(f"  Username: {MCPConfig.API_USERNAME}")
    print(f"  Queue Manager: {MCPConfig. QMGR_NAME}")
    
    print("\n1. Testing authentication...")
    try:
        token_manager = TokenManager(
            MCPConfig.FASTAPI_BASE_URL,
            MCPConfig.API_USERNAME,
            MCPConfig.API_PASSWORD
        )
        token = await token_manager.get_valid_token()
        print(f"   ✓ Success! Token: {token[:30]}...")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return
    
    print("\n2.  Testing queue manager status...")
    try:
        api_client = MQApiClient(token_manager)
        result = await api_client.get_queue_manager_status()
        print(f"   ✓ Success!")
        print(f"   Result: {result}")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    
    print("\n3. Testing queue list...")
    try:
        result = await api_client.get_queue_list()
        print(f"   ✓ Success!")
        print(f"   Found {len(result) if isinstance(result, list) else 'N/A'} queues")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(test())
EOF

# Run test
python test_mcp_direct.py
```

### Test 4: Check Debug Logs

```bash
# View debug log
tail -f mcp_server_debug.log
```

---

## Firewall Configuration

If you need to access the Inspector from another machine:

```bash
# Allow port 5173 (MCP Inspector web UI)
sudo firewall-cmd --permanent --add-port=5173/tcp

# Reload firewall
sudo firewall-cmd --reload

# Verify
sudo firewall-cmd --list-ports

# Check if port is listening
sudo netstat -tlnp | grep 5173
# or
sudo ss -tlnp | grep 5173
```

---

## Production Deployment

### 1. Use Reverse Proxy (nginx)

Install nginx:

```bash
sudo dnf install nginx -y
```

Create nginx configuration:

```bash
sudo nano /etc/nginx/conf.d/mcp-inspector.conf
```

```nginx
server {
    listen 80;
    server_name your-server-hostname.com;

    location / {
        proxy_pass http://localhost:5173;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Enable and start nginx:

```bash
sudo systemctl enable nginx
sudo systemctl start nginx

# Allow HTTP in firewall
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --reload
```

### 2. Set Up Log Rotation

```bash
sudo nano /etc/logrotate. d/mcp-inspector
```

```
/home/your_username/mq-mcp-server/*. log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 your_username your_username
}
```

Test log rotation:

```bash
sudo logrotate -d /etc/logrotate. d/mcp-inspector
```

### 3. Security Best Practices

```bash
# Secure .env file
chmod 600 ~/. env

# Set appropriate permissions
chmod 750 ~/mq-mcp-server
chmod 640 ~/mq-mcp-server/*. py

# Disable SELinux temporarily for testing (if needed)
sudo setenforce 0

# To permanently disable SELinux (not recommended for production)
sudo nano /etc/selinux/config
# Set: SELINUX=disabled
```

### 4.  Monitoring

Create monitoring script:

```bash
cat > monitor. sh << 'EOF'
#!/bin/bash

# Check if MCP server is running
if systemctl is-active --quiet mcp-mq-inspector; then
    echo "✓ MCP Inspector service is running"
else
    echo "✗ MCP Inspector service is NOT running"
    sudo systemctl status mcp-mq-inspector
fi

# Check if port is listening
if netstat -tlnp 2>/dev/null | grep -q :5173; then
    echo "✓ Port 5173 is listening"
else
    echo "✗ Port 5173 is NOT listening"
fi

# Check recent errors in logs
echo -e "\nRecent errors (last 10):"
sudo journalctl -u mcp-mq-inspector --priority=err -n 10 --no-pager
EOF

chmod +x monitor.sh
```

Run monitoring:

```bash
./monitor.sh
```

---

## Troubleshooting

### Issue: Python 3.11 not available

**Solution:**

```bash
# Enable EPEL repository
sudo dnf install epel-release -y

# Try installing from EPEL
sudo dnf install python3. 11 -y
```

### Issue: npm command not found

**Solution:**

```bash
# Reinstall Node.js
curl -fsSL https://rpm. nodesource.com/setup_20.x | sudo bash -
sudo dnf install nodejs -y

# Verify
which npm
npm --version
```

### Issue: Port 5173 already in use

**Solution:**

```bash
# Find process using port 5173
sudo lsof -i :5173

# Kill the process
sudo kill -9 <PID>

# Or find and kill in one command
sudo kill -9 $(sudo lsof -t -i:5173)
```

### Issue: Cannot access from remote machine

**Check firewall:**

```bash
# Check if firewall is running
sudo firewall-cmd --state

# List all allowed ports
sudo firewall-cmd --list-all

# Add port if missing
sudo firewall-cmd --permanent --add-port=5173/tcp
sudo firewall-cmd --reload
```

**Check if service is listening on all interfaces:**

```bash
# Should show 0.0.0.0:5173 or :::5173
sudo netstat -tlnp | grep 5173
```

### Issue: Authentication fails (401 error)

**Check credentials:**

```bash
# Verify . env file
cat .env

# Test authentication manually
curl -X POST "http://localhost:8000/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Password123"
```

### Issue: SELinux blocking connections

**Temporary disable:**

```bash
sudo setenforce 0
```

**Check SELinux status:**

```bash
sestatus
```

**View SELinux denials:**

```bash
sudo ausearch -m avc -ts recent
```

### Issue: Module 'mcp' not found

**Solution:**

```bash
# Ensure venv is activated
source ~/mq-mcp-server/venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt

# Verify installation
pip show mcp
```

### View Logs

```bash
# Service logs (if using systemd)
sudo journalctl -u mcp-mq-inspector -f

# Debug log
tail -f ~/mq-mcp-server/mcp_server_debug.log

# Last 50 lines
tail -50 ~/mq-mcp-server/mcp_server_debug.log
```

---

## Project Structure

```
~/mq-mcp-server/
├── venv/                          # Python virtual environment
├── .env                           # Environment variables (DO NOT COMMIT)
├── .gitignore                     # Git ignore file
├── mcp_mq_server.py              # Main MCP server
├── requirements.txt              # Python dependencies
├── start_inspector. sh            # Startup script
├── test_mcp_direct.py            # Test script
├── monitor. sh                    # Monitoring script
└── mcp_server_debug.log          # Debug log (created at runtime)
```

---

## Quick Command Reference

### Start/Stop Service

```bash
# Interactive mode
./start_inspector.sh

# Screen session
screen -S mcp-inspector
./start_inspector.sh
# Detach: Ctrl+A, D

# systemd service
sudo systemctl start mcp-mq-inspector
sudo systemctl stop mcp-mq-inspector
sudo systemctl restart mcp-mq-inspector
sudo systemctl status mcp-mq-inspector
```

### View Logs

```bash
# Service logs
sudo journalctl -u mcp-mq-inspector -f

# Debug logs
tail -f mcp_server_debug.log

# Error logs only
sudo journalctl -u mcp-mq-inspector --priority=err -n 50
```

### Check Status

```bash
# Service status
sudo systemctl status mcp-mq-inspector

# Port status
sudo netstat -tlnp | grep 5173

# Process status
ps aux | grep mcp_mq_server
```

---

## Adding New Endpoints

When your FastAPI application adds new endpoints, update these 5 sections in `mcp_mq_server.py`:

1. **MQApiClient class** - Add API method
2. **list_resources()** - Add resource definition
3. **read_resource()** - Add resource handler
4. **list_tools()** - Add tool definition
5. **call_tool()** - Add tool implementation

Example: Adding listener endpoint

```python
# 1. API Client Method
async def get_listener_status(self, qmgr_name: str = None) -> dict:
    qmgr = qmgr_name or self. qmgr_name
    return await self._make_request("GET", f"/qmgr/{qmgr}/listeners")

# 2. Resource Definition
Resource(
    uri=f"mq://{qmgr_name}/listeners/status",
    name=f"Listener Status - {qmgr_name}",
    mimeType="application/json",
    description=f"Status of MQ listeners"
)

# 3. Resource Handler
elif uri == f"mq://{qmgr_name}/listeners/status":
    data = await self. api_client.get_listener_status()
    return self._format_response(data)

# 4.  Tool Definition
Tool(
    name="get_listener_status",
    description="Get status of MQ listeners",
    inputSchema={"type": "object", "properties": {}, "required": []}
)

# 5.  Tool Implementation
elif name == "get_listener_status":
    qmgr_name = arguments. get("qmgr_name") if arguments else None
    result = await self.api_client. get_listener_status(qmgr_name)
```

---

## Support and Documentation

- **MCP Protocol:** https://modelcontextprotocol.io/

---

## License

MIT License

---

## Changelog

### v1.0.0 (2025-01-XX)
- Initial release
- Support for queue manager status, queues, and channels
- RHEL9 compatibility
- systemd service support
