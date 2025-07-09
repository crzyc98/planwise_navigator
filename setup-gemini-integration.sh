#!/bin/bash
set -e

echo "🚀 Setting up Gemini CLI Integration..."

# Check Node.js version
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found. Please install Node.js 18+ first."
    exit 1
fi

NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "❌ Node.js version $NODE_VERSION found. Please use Node.js 18+ (recommended: 22.16.0)"
    echo "   Use: nvm install 22.16.0 && nvm use 22.16.0"
    exit 1
fi

echo "✅ Node.js version check passed"

# Install Gemini CLI
echo "📦 Installing Gemini CLI..."
npm install -g @google/gemini-cli

# Test installation
echo "🧪 Testing Gemini CLI installation..."
if gemini --help > /dev/null 2>&1; then
    echo "✅ Gemini CLI installed successfully"
else
    echo "❌ Gemini CLI installation failed"
    exit 1
fi

# Files can be placed in the same directory - no complex structure needed
echo "📁 Setting up in current directory..."

# Create default configuration
echo "⚙️ Creating default configuration..."
cat > gemini-config.json << 'EOF'
{
  "enabled": true,
  "auto_consult": true,
  "cli_command": "gemini",
  "timeout": 60,
  "rate_limit_delay": 2.0,
  "max_context_length": 4000,
  "log_consultations": true,
  "model": "gemini-2.5-flash",
  "sandbox_mode": false,
  "debug_mode": false
}
EOF

# Create MCP configuration for Claude Code
echo "🔧 Creating Claude Code MCP configuration..."
cat > mcp-config.json << 'EOF'
{
  "mcpServers": {
    "project": {
      "command": "python3",
      "args": ["mcp-server.py", "--project-root", "."],
      "env": {
        "GEMINI_ENABLED": "true",
        "GEMINI_AUTO_CONSULT": "true"
      }
    }
  }
}
EOF

echo ""
echo "🎉 Gemini CLI Integration setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Copy the provided code files to your project:"
echo "   - gemini_integration.py"
echo "   - mcp-server.py"
echo "2. Install Python dependencies: pip install mcp pydantic"
echo "3. Test with: python3 mcp-server.py --project-root ."
echo "4. Configure Claude Code to use the MCP server"
echo ""
echo "💡 Tip: First run 'gemini' command to authenticate with your Google account"
