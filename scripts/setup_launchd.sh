#!/bin/bash
# Run this script to write launchd plists and load them.
# Detects your actual macOS username automatically.

USERNAME=$(whoami)
HOME_DIR="/Users/${USERNAME}"
AGENTS_DIR="${HOME_DIR}/Library/LaunchAgents"

mkdir -p "${AGENTS_DIR}"

# ── Triage plist (07:00 daily) ──
cat > "${AGENTS_DIR}/com.OWNER.jobpipeline.triage.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.OWNER.jobpipeline.triage</string>
  <key>ProgramArguments</key><array>
    <string>/opt/homebrew/bin/python3</string>
    <string>${HOME_DIR}/JobSearchPipeline/scripts/triage.py</string>
  </array>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>7</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
    <string>${HOME_DIR}/JobSearchPipeline/logs/launchd_triage_stdout.log</string>
  <key>StandardErrorPath</key>
    <string>${HOME_DIR}/JobSearchPipeline/logs/launchd_triage_stderr.log</string>
  <key>RunAtLoad</key><false/>
</dict></plist>
EOF

# ── Flag poller plist (every 30 min) ──
cat > "${AGENTS_DIR}/com.OWNER.jobpipeline.poller.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.OWNER.jobpipeline.poller</string>
  <key>ProgramArguments</key><array>
    <string>/opt/homebrew/bin/python3</string>
    <string>${HOME_DIR}/JobSearchPipeline/scripts/poll_flags.py</string>
  </array>
  <key>StartInterval</key><integer>1800</integer>
  <key>StandardOutPath</key>
    <string>${HOME_DIR}/JobSearchPipeline/logs/launchd_poller_stdout.log</string>
  <key>StandardErrorPath</key>
    <string>${HOME_DIR}/JobSearchPipeline/logs/launchd_poller_stderr.log</string>
  <key>RunAtLoad</key><false/>
</dict></plist>
EOF

# ── Weekly RAG rebuild plist (Sunday 06:00) ──
# Note: --rag <name> and --rebuild-rag must both be present (divergence log #34)
cat > "${AGENTS_DIR}/com.OWNER.jobpipeline.rag.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.OWNER.jobpipeline.rag</string>
  <key>ProgramArguments</key><array>
    <string>/usr/local/bin/aichat-ng</string>
    <string>--rag</string>
    <string>job_search_rag</string>
    <string>--rebuild-rag</string>
  </array>
  <key>StartCalendarInterval</key><dict>
    <key>Weekday</key><integer>0</integer>
    <key>Hour</key><integer>6</integer>
  </dict>
  <key>RunAtLoad</key><false/>
</dict></plist>
EOF

echo "Plists written to ${AGENTS_DIR}/"
echo ""

# ── Reload all three ──
launchctl unload "${AGENTS_DIR}/com.OWNER.jobpipeline.triage.plist" 2>/dev/null
launchctl unload "${AGENTS_DIR}/com.OWNER.jobpipeline.poller.plist" 2>/dev/null
launchctl unload "${AGENTS_DIR}/com.OWNER.jobpipeline.rag.plist" 2>/dev/null

launchctl load "${AGENTS_DIR}/com.OWNER.jobpipeline.triage.plist"
launchctl load "${AGENTS_DIR}/com.OWNER.jobpipeline.poller.plist"
launchctl load "${AGENTS_DIR}/com.OWNER.jobpipeline.rag.plist"

echo "Loaded. Verify with:"
echo "  launchctl list | grep brock"
