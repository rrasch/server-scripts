#!/usr/bin/python3

import os
import pwd
import requests
import shutil
import signal
import socket
import subprocess
import time
from datetime import datetime
from getpass import getpass
from pprint import pprint


WOWZA_USER = "ams"
WOWZA_ADMIN_USER = "dltsadmin"
WOWZA_PUBLISH_USER = "dltspublish"
WOWZA_DIR = "/usr/local/WowzaStreamingEngine"
WOWZA_CONTENT_DIR = "/data/adobe/ams/content"
SYSTEMD_DIR = "/etc/systemd/system"

LIMITS_FILE = "/etc/security/limits.d/99-wowza.conf"

EXPECTED_SERVICES = [
    "WowzaStreamingEngine.service",
    "WowzaStreamingEngineManager.service",
]

EXPECTED_PORTS = [1935, 8088]

API_URL = "http://localhost:8087/v2/servers/_defaultServer_/tune"
API_HEADERS = {
    "Accept": "application/json; charset=utf-8",
    "Content-Type": "application/json; charset=utf-8"
}

# ---------------------------
# helpers
# ---------------------------

def run(cmd):
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def find_services():
    found = {}

    for root, _, files in os.walk(WOWZA_DIR):
        for f in files:
            if f.endswith(".service"):
                found[f] = os.path.join(root, f)

    return found


def install_service(name, path):
    target = os.path.join(SYSTEMD_DIR, name)

    if not os.path.exists(path):
        raise RuntimeError(f"Missing service file on disk: {path}")

    if os.path.exists(target):
        print(f"Already installed: {name}")
        return

    print(f"Installing: {name}")
    os.symlink(path, target)


def wowza_user_exists(username=WOWZA_USER):
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def install_wowza_license():
    license_path = os.path.join(WOWZA_DIR, "conf", "Server.license")

    # 1. Idempotent check
    if os.path.exists(license_path):
        print("License file already exists, skipping.")
        return

    # 2. Env var first
    license_key = os.getenv("WOWZA_LICENSE_KEY")

    # 3. Fallback to input
    if not license_key:
        license_key = input("Enter Wowza license key: ").strip()

    if not license_key:
        raise RuntimeError("No license key provided")

    # 4. Write file
    print("Writing license file...")

    with open(license_path, "w") as f:
        f.write(license_key + "\n")

    os.chmod(license_path, 0o600)

    print(f"License installed at {license_path}")


def set_wowza_ownership():
    print(f"Setting ownership of {WOWZA_DIR} to {WOWZA_USER}:{WOWZA_USER}")

    subprocess.run([
        "chown",
        "-R",
        "-H",
        f"{WOWZA_USER}:{WOWZA_USER}",
        WOWZA_DIR
    ], check=True)


def create_systemd_override(service_name):
    override_dir = os.path.join(
        SYSTEMD_DIR,
        service_name + ".d"
    )

    override_file = os.path.join(override_dir, "override.conf")

    print(f"Creating systemd override for {service_name}")

    os.makedirs(override_dir, exist_ok=True)

    with open(override_file, "w") as f:
        f.write(
            "[Service]\n"
            f"User={WOWZA_USER}\n"
            f"Group={WOWZA_USER}\n"
            "LimitNOFILE=20000\n"
        )

    subprocess.run(["systemctl", "daemon-reload"], check=True)


def require_root():
    if os.geteuid() != 0:
        raise RuntimeError("This script must be run as root (use sudo)")


def install_lsb_release():
    """
    Ensures lsb_release command is installed.
    """

    if shutil.which("lsb_release"):
        print("lsb_release already installed")
        return

    print("Installing lsb_release...")

    subprocess.run(
        ["dnf", "install", "-y", "lsb_release"],
        check=True
    )


def admin_user_exists(password_file, username=WOWZA_ADMIN_USER):
    """
    Checks whether a user exists in admin.password file.
    """
    with open(password_file, "r") as f:
        for line in f:
            # format is typically: user:hash:groups
            if line.startswith(username + " "):
                return True
    return False


def create_admin_user():
    """
    Creates Wowza admin user only if it does not already exist.
    """

    tool_path = os.path.join(WOWZA_DIR, "bin", "passwordtool.sh")
    password_file = os.path.join(WOWZA_DIR, "conf", "admin.password")

    if not os.path.exists(tool_path):
        raise RuntimeError(f"passwordtool.sh not found: {tool_path}")

    if not os.path.exists(password_file):
        raise RuntimeError(f"admin.password file not found: {password_file}")

    # Idempotency check
    if admin_user_exists(password_file, WOWZA_ADMIN_USER):
        print("Admin user already exists, skipping creation.")
        return

    password = getpass("Enter Wowza admin password: ")
    if not password:
        raise RuntimeError("Password cannot be empty")

    print("Creating Wowza admin user...")

    subprocess.run([
        tool_path,
        "-f", password_file,
        "--addUser",
        "--userName", WOWZA_ADMIN_USER,
        "--password", password,
        "--groups", "admin,advUser",
        "--passwordEncoding", "bcrypt"
    ], check=True)

    print("Admin user created successfully.")


def create_publish_user():
    """
    Create Wowza live stream publish user only if it doesn't exist.

    Returns password of publish user.
    """

    path = os.path.join(WOWZA_DIR, "conf", "publish.password")

    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing password file: {path}")

    # 1. Try to find existing password
    with open(path, "r") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split()

            if len(parts) >= 2 and parts[0] == WOWZA_PUBLISH_USER:
                print("Wowza publish user already exists.")
                return parts[1]

    print("Creating Wowza publish user...")

    # 2. Not found → prompt user
    password = getpass("Enter publish password: ")

    if not password:
        raise ValueError("Password cannot be empty")

    # 3. Append new entry
    with open(path, "a") as f:
        f.write(f"{WOWZA_PUBLISH_USER} {password}\n")

    return password


def ensure_wowza_nofile_limits(user=WOWZA_USER, limit=20000):
    """
    Ensures Wowza file descriptor limits exist via limits.d drop-in file.
    """

    if os.path.exists(LIMITS_FILE):
        print(f"Limits file already exists: {LIMITS_FILE}")
        return

    print("Creating Wowza limits.d configuration...")

    content = (
        f"{user} soft nofile {limit}\n"
        f"{user} hard nofile {limit}\n"
    )

    with open(LIMITS_FILE, "w") as f:
        f.write(content)

    os.chmod(LIMITS_FILE, 0o644)

    print("Limits file created successfully.")


def update_storage_dir():
    """
    Update StorageDir in all Application.xml files under Wowza conf directory.
    Creates timestamped backups only for modified files.
    """

    default_content_dir = "${com.wowza.wms.context.VHostConfigHome}/content"
    old_line = f"<StorageDir>{default_content_dir}</StorageDir>"
    new_line = f"<StorageDir>{WOWZA_CONTENT_DIR}</StorageDir>"

    conf_dir = os.path.join(WOWZA_DIR, "conf")

    updated_any = False
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for root, _, files in os.walk(conf_dir):
        for name in files:
            if name != "Application.xml":
                continue

            path = os.path.join(root, name)

            with open(path, "r") as f:
                content = f.read()

            if old_line not in content:
                print(f"Default StorageDir not found in {path}, skipping.")
                continue

            new_content = content.replace(old_line, new_line)

            if new_content == content:
                print(f"StorageDir already set in {path}, skipping.")
                continue

            backup_path = f"{path}.{timestamp}.bak"
            shutil.copy2(path, backup_path)
            print(f"Backup created: {backup_path}")

            with open(path, "w") as f:
                f.write(new_content)

            print(f"Updated StorageDir in: {path}")
            updated_any = True

    if not updated_any:
        print("No Application.xml files required updates.")
    else:
        print("StorageDir update completed.")


def copy_wowza_content():
    """
    Recursively copy WOWZA_DIR/content to WOWZA_CONTENT_DIR
    without overwriting existing files.
    """

    src = os.path.join(WOWZA_DIR, "content")
    dst = WOWZA_CONTENT_DIR

    print(f"Copying content from {src} -> {dst}")

    if not os.path.exists(src):
        raise FileNotFoundError(f"Source directory not found: {src}")

    if not os.access(dst, os.W_OK):
        print(f"Destination is read-only, skipping copy: {dst}")
        return

    for root, dirs, files in os.walk(src):
        rel_path = os.path.relpath(root, src)
        target_root = os.path.join(dst, rel_path) if rel_path != "." else dst

        os.makedirs(target_root, exist_ok=True)

        for name in files:
            src_file = os.path.join(root, name)
            dst_file = os.path.join(target_root, name)

            # skip if already exists
            if os.path.exists(dst_file):
                print(f"Skipping existing file: {dst_file}")
                continue

            shutil.copy2(src_file, dst_file)
            print(f"Copied: {src_file} -> {dst_file}")

    print("Content copy completed.")


def get_current_tuning():
    """Retrieve current server tuning settings"""
    try:
        response = requests.get(
            API_URL,
            auth=("admin", "admin"),
            headers=API_HEADERS,
        )
        response.raise_for_status()  # Raises an error for bad status codes
        print("Current Tuning Settings:")
        pprint(response.json())
    except requests.exceptions.RequestException as e:
        print(f"Error fetching settings: {e}")


def enable_production_mode():
    """Update server to Production Mode settings"""
    payload = {
        "heapSize": "${com.wowza.wms.TuningHeapSizeProduction}",
        # "garbageCollector": "${com.wowza.wms.TuningGarbageCollectorG1Default}"
    }

    try:
        response = requests.put(
            API_URL,
            auth=("admin", "admin"),
            headers=API_HEADERS,
            json=payload
        )
        response.raise_for_status()
        print("Successfully updated to Production Mode.")
        pprint(response.json())
    except requests.exceptions.RequestException as e:
        print(f"Error updating settings: {e}")


def drop_privileges(user_name="nobody"):
    if os.getuid() != 0:
        return  # Already running as non-root

    # Get the UID/GID for the specified user
    user_info = pwd.getpwnam(user_name)

    # 1. Set the process group ID
    os.setgid(user_info.pw_gid)
    # 2. Set the process user ID
    os.setuid(user_info.pw_uid)

    # Optional: Update environment variables like HOME
    os.environ["HOME"] = user_info.pw_dir


# ---------------------------
# systemd operations
# ---------------------------

def reload_systemd():
    run(["systemctl", "daemon-reload"])


def enable_and_start(service):
    unit = service.replace(".service", "")

    run(["systemctl", "enable", unit])
    run(["systemctl", "stop", unit])
    time.sleep(5)
    run(["systemctl", "start", unit])


def is_active(service):
    unit = service.replace(".service", "")
    result = subprocess.run(
        ["systemctl", "is-active", unit],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() == "active"


# ---------------------------
# port checks
# ---------------------------

def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_ports(timeout=30):
    print("\nChecking ports...")

    start = time.time()
    while time.time() - start < timeout:
        open_ports = [p for p in EXPECTED_PORTS if check_port(p)]

        if len(open_ports) == len(EXPECTED_PORTS):
            print(f"All ports open: {EXPECTED_PORTS}")
            return True

        time.sleep(2)

    raise RuntimeError(f"Ports not ready: {EXPECTED_PORTS}")


# ---------------------------
# playback readiness
# ---------------------------

def start_test_stream(publish_pass):
    """
    Starts a short FFmpeg test stream to Wowza.
    Returns the subprocess handle.
    """
    cmd = [
        "ffmpeg",
        "-re",
        "-f", "lavfi",
        "-i", "testsrc=size=1280x720:rate=30",
        "-f", "lavfi",
        "-i", "sine=frequency=1000",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-t", "20",
        "-f", "flv",
        f"rtmp://{WOWZA_PUBLISH_USER}:{publish_pass}@127.0.0.1/live/test",
    ]

    env = os.environ.copy()
    env["PATH"] = "/usr/local/bin:" + env["PATH"]

    print("Starting FFmpeg test stream...")
    print("Running command", " ".join(cmd))

    return subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )


def check_playback_readiness(
    host="127.0.0.1",
    app="live",
    stream="test",
    timeout=30
):
    """
    Verifies playback readiness via HLS manifest availability.
    """
    url = f"http://{host}:1935/{app}/{stream}/playlist.m3u8"
    # url = f"http://{host}:1935/vod/mp4:sample.mp4/playlist.m3u8"

    print(f"Checking playback readiness: {url}")

    start = time.time()

    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=5)

            if r.status_code == 200 and "#EXTM3U" in r.text:
                print("Playback READY (HLS manifest valid)")
                return True

        except requests.RequestException:
            pass

        time.sleep(2)

    raise RuntimeError("Playback NOT ready (HLS not available)")


def run_playback_test(publish_pass):
    """
    Runs full end-to-end playback test:
    starts FFmpeg → waits → validates HLS → stops FFmpeg
    """
    proc = start_test_stream(publish_pass)

    try:
        time.sleep(3)  # give Wowza time to start ingest
        check_playback_readiness()
    finally:
        print("Stopping FFmpeg test stream...")
        try:
            # proc.terminate()
            proc.send_signal(signal.SIGINT)
            stdout, stderr = proc.communicate(timeout=5)
        except Exception:
            proc.kill()
            stdout, stderr = proc.communicate()

        if proc.returncode not in (0, 255, None):
            print(f"\nFFmpeg return code: {proc.returncode}")
            print("FFmpeg error output:")
            print(stderr)


# ---------------------------
# main flow
# ---------------------------

def main():
    print("\n=== Wowza Bootstrap Starting ===\n")

    require_root()

    if not wowza_user_exists():
        raise RuntimeError(
            f"Required system user '{WOWZA_USER}' does not exist. "
            "Create it before running bootstrap."
        )

    install_lsb_release()

    ensure_wowza_nofile_limits()

    update_storage_dir()

    install_wowza_license()

    create_admin_user()

    publish_pass = create_publish_user()

    set_wowza_ownership()

    copy_wowza_content()

    found = find_services()

    print("Expected services:")
    for svc in EXPECTED_SERVICES:
        print(f" - {svc}: {found.get(svc)}")
        if svc not in found:
            raise RuntimeError(f"Missing expected service: {svc}")

    print("\nInstalling services...")
    for svc in EXPECTED_SERVICES:
        install_service(svc, found[svc])
        create_systemd_override(svc)

    reload_systemd()

    print("\nEnabling + starting services...")
    for svc in EXPECTED_SERVICES:
        enable_and_start(svc)

    print("\nValidating systemd state...")
    for svc in EXPECTED_SERVICES:
        if not is_active(svc):
            raise RuntimeError(f"Service not active: {svc}")
        print(f"OK: {svc} is active")

    drop_privileges()

    wait_for_ports()

    get_current_tuning()

    enable_production_mode()

    run_playback_test(publish_pass)

    print("\n=== Wowza Bootstrap Complete ===")


if __name__ == "__main__":
    main()
