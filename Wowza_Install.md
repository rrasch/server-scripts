# Wowza Bootstrap

A Python bootstrap utility that automates the initial configuration and validation of a Wowza Streaming Engine installation on Linux.

The script configures Wowza, installs and enables its systemd services, creates the required users, applies production settings, and performs end-to-end streaming validation using FFmpeg.

The script is designed to be **idempotent** whenever possible, allowing it to be safely re-run without unnecessarily modifying an already configured system.

---

## Features

- Verifies required system user exists
- Installs missing system dependencies
- Configures file descriptor (`nofile`) limits
- Installs Wowza license
- Creates Wowza administrator account
- Creates Wowza publish account
- Updates Wowza storage directory
- Copies Wowza content files
- Sets proper file ownership
- Installs Wowza systemd services
- Creates systemd override files
- Enables and starts Wowza services
- Verifies required network ports are listening
- Enables Wowza Production Mode
- Performs an end-to-end live streaming test using FFmpeg
- Verifies Video-on-Demand (VOD) playback


---

## Bootstrap Workflow

```text
Start
  │
  ▼
Verify root privileges
  │
  ▼
Verify Wowza user
  │
  ▼
Install dependencies
  │
  ▼
Configure Wowza
  │
  ├─ Install license
  ├─ Create admin user
  ├─ Create publish user
  ├─ Update StorageDir
  ├─ Copy content
  └─ Set ownership
  │
  ▼
Install systemd services
  │
  ▼
Enable & start services
  │
  ▼
Verify services
  │
  ▼
Wait for ports
  │
  ▼
Enable Production Mode
  │
  ▼
Live stream test (FFmpeg)
  │
  ▼
Verify HLS playback
  │
  ▼
Verify VOD playback
  │
  ▼
Bootstrap Complete
```

---

## Requirements

- Linux
- Python 3
- Wowza Streaming Engine installed
- FFmpeg installed
- Root privileges
- Python package:

```bash
pip install requests
```

---

## Expected Installation

The script assumes the following directory layout:

| Item | Location |
|------|----------|
| Wowza installation | `/usr/local/WowzaStreamingEngine` |
| Content directory | `/data/adobe/ams/content` |
| systemd services | `/etc/systemd/system` |

---

## Required System User

The bootstrap expects the following Linux user to already exist:

```
ams
```

If the user does not exist, the script terminates immediately.

---

## What the Script Configures

### 1. System

- Installs `lsb_release` if missing
- Creates:

```
/etc/security/limits.d/99-wowza.conf
```

to increase the Wowza file descriptor limit.

---

### 2. Wowza Configuration

- Installs the Wowza license
- Creates the administrator account
- Creates the publishing account
- Changes ownership of the Wowza installation
- Updates every `Application.xml` to use

```
/data/adobe/ams/content
```

instead of the default content directory.

A timestamped backup is created before any `Application.xml` is modified.

---

### 3. Content

Copies the default Wowza content into

```
/data/adobe/ams/content
```

Existing files are never overwritten.

---

### 4. systemd

The script:

- Finds the Wowza service files
- Installs them into `/etc/systemd/system`
- Creates override files
- Reloads systemd
- Enables the services
- Restarts the services
- Verifies they are running

---

### 5. Network Validation

The bootstrap waits until the following ports are accepting connections:

- 1935 (RTMP)
- 8088 (Wowza Manager)

---

### 6. Production Mode

The script connects to the Wowza REST API and updates the server tuning to use the Production heap size.

---

### 7. Streaming Validation

The script performs an automated end-to-end validation.

It:

1. Starts an FFmpeg-generated test stream.
2. Publishes it to Wowza via RTMP.
3. Waits for the HLS playlist to become available.
4. Stops FFmpeg.
5. Verifies Video-on-Demand playback.

If any step fails, the bootstrap exits with an error.

---

## Running

Execute as root:

```bash
sudo ./wowza-bootstrap.py
```

or

```bash
sudo python3 wowza-bootstrap.py
```

---

## User Prompts

During execution the script may prompt for:

- Wowza license key
- Wowza administrator password
- Wowza publish password

The license key may also be supplied using:

```bash
export WOWZA_LICENSE_KEY=<license key>
```

---

## Idempotency

Most operations are safe to execute multiple times.

Examples include:

- Existing administrator user is not recreated
- Existing publish user is not recreated
- Existing license file is left unchanged
- Existing service symlinks are preserved
- Existing content files are skipped
- Existing limits configuration is preserved
- Storage directory updates are only applied when necessary

---

## Validation

The bootstrap verifies:

- Required Linux user exists
- Wowza services exist
- Services start successfully
- Services are active
- Required ports are open
- Wowza REST API is reachable
- Production tuning is applied
- Live streaming functions correctly
- HLS playback is available
- Video-on-Demand playback is available

---

## Exit Conditions

The script terminates immediately if any critical step fails, including:

- Missing Wowza installation
- Missing service files
- Missing password files
- Missing content directory
- Missing Linux user
- Failure to start services
- Network ports never become available
- REST API failures
- Streaming validation failures

---

## Notes

- The script must be executed with root privileges.
- After the Wowza services have been started, privileges are dropped before performing network validation and streaming tests.
- All critical operations raise exceptions on failure, causing the bootstrap to terminate immediately.
