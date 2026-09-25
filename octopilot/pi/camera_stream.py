import cv2
import socket
import struct
import signal
import time


# ============================================================
# CAMERA SETTINGS
# ============================================================

CAMERA_ID = 0
WIDTH = 800
HEIGHT = 600
CAMERA_FPS = 60

# Camera runs at 60 FPS. Send every 4th frame = ~15 FPS.
SEND_EVERY = 4
JPEG_QUALITY = 80

# ============================================================
# DESKTOP
# ============================================================

DESKTOP_IP = "192.168.0.203"

PORTS = {
    "rpi27": 6027,
    "rpi29": 6029,
    "rpi33": 6033,
    "rpi34": 6034,
}

# ============================================================
# IDENTIFY THIS PI
# ============================================================

HOSTNAME = socket.gethostname()

if HOSTNAME not in PORTS:
    raise RuntimeError(f"Unknown Pi hostname: {HOSTNAME}")

PORT = PORTS[HOSTNAME]

print(f"Running camera stream on {HOSTNAME}")
print(f"Desktop: {DESKTOP_IP}:{PORT}")

# ============================================================
# CLEAN STOP
# ============================================================

running = True

def stop_stream(signum, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, stop_stream)
signal.signal(signal.SIGINT, stop_stream)

# ============================================================
# OPEN CAMERA
# ============================================================

camera = cv2.VideoCapture(CAMERA_ID, cv2.CAP_V4L2)

if not camera.isOpened():
    raise RuntimeError(f"{HOSTNAME}: could not open /dev/video{CAMERA_ID}")

camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
camera.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
camera.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

actual_width = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
actual_height = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
actual_fps = camera.get(cv2.CAP_PROP_FPS)

print(f"Camera opened: {actual_width}x{actual_height} @ {actual_fps:.2f} FPS")

if actual_width != WIDTH or actual_height != HEIGHT:
    print("WARNING: Camera did not accept the requested resolution.")

# ============================================================
# CONNECT TO DESKTOP
# ============================================================

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(2.0)

try:
    print("Connecting to desktop...")
    sock.connect((DESKTOP_IP, PORT))
    print("Connected to desktop.")
except Exception as error:
    print(f"Could not connect to desktop: {error}")
    camera.release()
    sock.close()
    raise SystemExit

# ============================================================
# STREAM FRAMES
# ============================================================

captured_frames = 0
sent_frames = 0

try:
    while running:
        success, frame = camera.read()

        if not success:
            print("WARNING: Camera frame failed")
            time.sleep(0.01)
            continue

        captured_frames += 1

        if captured_frames % SEND_EVERY != 0:
            continue

        success, encoded = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        )

        if not success:
            continue

        frame_data = encoded.tobytes()

        try:
            header = struct.pack(">L", len(frame_data))
            sock.sendall(header)
            sock.sendall(frame_data)
        except (
            socket.timeout,
            BrokenPipeError,
            ConnectionResetError,
            ConnectionAbortedError,
            OSError
        ) as error:
            print(f"Desktop connection lost: {error}")
            break

        sent_frames += 1

except Exception as error:
    print(f"Camera stream error: {error}")

finally:
    camera.release()

    try:
        sock.shutdown(socket.SHUT_RDWR)
    except Exception:
        pass

    try:
        sock.close()
    except Exception:
        pass

    print()
    print(f"{HOSTNAME} camera stopped.")
    print(f"Camera frames captured: {captured_frames}")
    print(f"Frames sent to desktop: {sent_frames}")
