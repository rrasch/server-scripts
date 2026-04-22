#!/usr/bin/python3

import os
import pwd
import requests
import shutil
import socket
import subprocess
import time

WOWZA_USER = "ams"
WOWZA_ADMIN_USER = "dltsadmin"
WOWZA_DIR = "/usr/local/WowzaStreamingEngine"
SYSTEMD_DIR = "/etc/systemd/system"

LIMITS_FILE = "/etc/security/limits.d/99-wowza.conf"

EXPECTED_SERVICES = [
    "WowzaStreamingEngine.service",
    "WowzaStreamingEngineManager.service",
]

EXPECTED_PORTS = [1935, 8088]


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
        "-v",
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

    password = input("Enter Wowza admin password: ").strip()
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

def start_test_stream():
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
        "rtmp://publish:publish@127.0.0.1/live/test",
    ]

    env = os.environ.copy()
    env["PATH"] = "/usr/local/bin:" + env["PATH"]

    print("Starting FFmpeg test stream...")
    print(" ".join(cmd))
    print(env["PATH"])

    return subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


def run_playback_test():
    """
    Runs full end-to-end playback test:
    starts FFmpeg → waits → validates HLS → stops FFmpeg
    """
    proc = start_test_stream()

    try:
        time.sleep(3)  # give Wowza time to start ingest
        check_playback_readiness()
    finally:
        print("Stopping FFmpeg test stream...")
        proc.terminate()
        proc.wait()


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

    install_wowza_license()

    create_admin_user()

    set_wowza_ownership()

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

    wait_for_ports()

    run_playback_test()

    print("\n=== Wowza Bootstrap Complete ===")


if __name__ == "__main__":
    main()
