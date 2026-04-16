# macOS Setup (Homebrew + launchd)

Tested on macOS 14+ (Apple Silicon and Intel).

---

## 1. Install Homebrew Dependencies

```bash
brew install python pandoc rclone
```

Verify:
```bash
/opt/homebrew/bin/python3 --version   # should be 3.11+
/opt/homebrew/bin/pandoc --version
/opt/homebrew/bin/rclone version
```

---

## 2. Install Rust and aichat-ng

```bash
# Install Rust (if not already installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Build aichat-ng
git clone https://github.com/sigoden/aichat /tmp/aichat-ng-build
cd /tmp/aichat-ng-build
cargo build --release
sudo cp target/release/aichat /usr/local/bin/aichat-ng
/usr/local/bin/aichat-ng --version
```

---

## 3. Clone the Repository

```bash
git clone https://github.com/yourname/findajob ~/findajob
cd ~/findajob
```

---

## 4. Install Python Dependencies

```bash
/opt/homebrew/bin/pip3 install --break-system-packages \
  google-api-python-client \
  google-auth-httplib2 \
  google-auth-oauthlib \
  requests \
  jsonschema \
  beautifulsoup4
```

---

## 5. Create Personal Config Files

```bash
cd ~/findajob
cp candidate_context/profile.md.example candidate_context/profile.md
cp config/jsearch_queries.txt.example config/jsearch_queries.txt
cp config/feed_urls.txt.example config/feed_urls.txt
cp config/target_companies.md.example config/target_companies.md
cp CLAUDE.local.md.example CLAUDE.local.md
cp data/.env.example data/.env && chmod 600 data/.env
```

Edit each file. See [configure.md](configure.md).

---

## 6. Create Binary Path Config

```bash
cp config/paths.env.example config/paths.env
```

Edit `config/paths.env`:
```bash
AICHAT_NG=/usr/local/bin/aichat-ng
PANDOC=/opt/homebrew/bin/pandoc
RCLONE=/opt/homebrew/bin/rclone
```

---

## 7. Configure aichat-ng

Config directory on macOS:
```bash
mkdir -p ~/Library/Application\ Support/aichat_ng/
```

Create `~/Library/Application Support/aichat_ng/config.yaml`:
```yaml
model: gemini:gemini-3-flash-preview

clients:
  - type: gemini
    api_key: ${GOOGLE_API_KEY}

  - type: claude
    api_key: ${ANTHROPIC_API_KEY}

  - type: openrouter
    api_key: ${OPENROUTER_API_KEY}

  - type: perplexity
    api_key: ${PERPLEXITY_API_KEY}

  - type: gemini
    name: gemini-embed
    api_key: ${GOOGLE_API_KEY}
    models:
      - name: gemini-embedding-001
        max_input_tokens: 2048

roles_dir: ~/findajob/config/roles
```

Source your API keys before using aichat-ng. Add to `~/.zshrc`:
```bash
set -a; source ~/findajob/data/.env; set +a
```

---

## 8. Set Up the Database

```bash
/opt/homebrew/bin/python3 scripts/init_db.py
sqlite3 data/pipeline.db ".tables"
# Expected: audit_log  feedback_log  jobs
```

---

## 9. Set Up Google Sheets

```bash
cp /path/to/gsheets_creds.json config/gsheets_creds.json
echo "YOUR_SHEET_ID" > config/sheet_id.txt
/opt/homebrew/bin/python3 scripts/setup_sheets.py
```

---

## 10. Set Up launchd Scheduler

launchd plist files live at `~/Library/LaunchAgents/`. The pipeline includes all plists.
Run the setup script:

```bash
bash scripts/setup_launchd.sh
```

Or manually load each plist:
```bash
launchctl load ~/Library/LaunchAgents/com.findajob.triage.plist
launchctl load ~/Library/LaunchAgents/com.findajob.poller.plist
# ... etc
```

Verify timers are loaded:
```bash
launchctl list | grep findajob
```

---

## 11. Verify the Install

```bash
# Test aichat-ng
echo "Hello" | /usr/local/bin/aichat-ng -m gemini:gemini-3-flash-preview -S "Say hi back"

# Test DB
sqlite3 ~/findajob/data/pipeline.db "SELECT count(*) FROM jobs;"

# Test Sheet connection
/opt/homebrew/bin/python3 scripts/sync_sheet.py

# Run a manual test notification
/opt/homebrew/bin/python3 scripts/notify.py health-check
```

---

## Scheduler Reference

| launchd label | Script | Schedule |
|---|---|---|
| `com.findajob.triage` | triage.py | 7:00 AM daily |
| `com.findajob.poller` | poll_flags.py | Every 10 min |
| `com.findajob.jobsync` | rclone copy --update | Every 15 min |
| `com.findajob.form-ingest` | ingest_form.py | Every 30 min |
| `com.findajob.rag-rebuild` | aichat-ng --rag rebuild | Sunday 6:00 AM |
| `com.findajob.notify-stats` | notify.py daily-stats | 7:05 AM daily |
| `com.findajob.notify-health` | notify.py health-check | 9:10 AM daily |
| `com.findajob.notify-issues` | notify.py issues-ping | Mon/Wed/Fri 8:00 AM |
| `com.findajob.notify-apply` | notify.py apply-reminder | 5:00 AM daily |
| `com.findajob.notify-feedback` | notify.py feedback-review | Sunday 8:00 AM |
