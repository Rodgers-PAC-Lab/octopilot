import cv2
import socket
import struct
import subprocess
import threading
import numpy as np
import os
import csv
import time
from datetime import datetime


# ============================================================
# CUBBIES / RASPBERRY PIS
# ============================================================

CUBBIES = {
    "cubbyA": {
        "hostname": "rpi27",
        "ip": "192.168.0.127",
        "port": 6027,
    },
    "cubbyB": {
        "hostname": "rpi29",
        "ip": "192.168.0.129",
        "port": 6029,
    },
    "cubbyC": {
        "hostname": "rpi33",
        "ip": "192.168.0.133",
        "port": 6033,
    },
    "cubbyD": {
        "hostname": "rpi34",
        "ip": "192.168.0.134",
        "port": 6034,
    },
}

# ============================================================
# CHOOSE WHICH CUBBIES TO USE
# ============================================================

# Current one-camera test:
ACTIVE_CUBBIES = [
    "cubbyB",
]

# For normal four-cubby recording, replace the above with:
#
# ACTIVE_CUBBIES = [
#     "cubbyA",
#     "cubbyB",
#     "cubbyC",
#     "cubbyD",
# ]

# ============================================================
# PI SETTINGS
# ============================================================

PI_USER = "pi"
PI_SCRIPT = "/home/pi/dev/octopilot/octopilot/pi/camera_stream.py"
PI_LOG = "/home/pi/camera.log"

# ============================================================
# RECORDING SETTINGS
# ============================================================

WIDTH = 800
HEIGHT = 600
FPS = 15

# ============================================================
# PREVIEW SETTINGS
# ============================================================

# Preview only. MKV files remain 800x600.
PREVIEW_WIDTH = 320
PREVIEW_HEIGHT = 240

# ============================================================
# CHECK ACTIVE CUBBIES
# ============================================================

for cubby in ACTIVE_CUBBIES:
    if cubby not in CUBBIES:
        raise ValueError(f"Unknown cubby in ACTIVE_CUBBIES: {cubby}")

if len(ACTIVE_CUBBIES) == 0:
    raise ValueError("ACTIVE_CUBBIES cannot be empty.")

if len(ACTIVE_CUBBIES) > 4:
    raise ValueError("Maximum of four active cubbies.")

# ============================================================
# SESSION
# ============================================================

now = datetime.now()
DATE_STRING = now.strftime("%Y%m%d")
SESSION_STRING = now.strftime("%Y%m%d_%H%M%S")

SAVE_DIR = f"/home/mouse/Videos/{DATE_STRING}_behavior_videos"
os.makedirs(SAVE_DIR, exist_ok=True)

print()
print("========================================")
print(" Behavior Camera System")
print("========================================")
print()
print(f"Session: {SESSION_STRING}")
print()
print("Active cubbies:")

for cubby in ACTIVE_CUBBIES:
    info = CUBBIES[cubby]
    print(f"  {cubby}: {info['hostname']} ({info['ip']})")

print()
print("Saving videos to:")
print(SAVE_DIR)
print()

# ============================================================
# SHARED DATA
# ============================================================

frames = {cubby: None for cubby in ACTIVE_CUBBIES}
status = {cubby: "WAITING" for cubby in ACTIVE_CUBBIES}
frame_counts = {cubby: 0 for cubby in ACTIVE_CUBBIES}

recording = True
session_start = time.perf_counter()

# ============================================================
# RECEIVE ONE CAMERA
# ============================================================

def receive_camera(cubby, port):
    global recording

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.settimeout(1.0)

    try:
        server.bind(("0.0.0.0", port))
        server.listen(1)
    except Exception as error:
        print(f"{cubby}: server error: {error}")
        status[cubby] = "ERROR"
        return

    print(f"{cubby}: waiting on port {port}")

    connection = None

    while recording:
        try:
            connection, address = server.accept()
            break
        except socket.timeout:
            continue
        except Exception as error:
            print(f"{cubby}: connection error: {error}")
            status[cubby] = "ERROR"
            server.close()
            return

    if connection is None:
        server.close()
        return

    connection.settimeout(2.0)

    print(f"{cubby}: connected from {address[0]}")
    status[cubby] = "RECORDING"

    video_filename = os.path.join(
        SAVE_DIR,
        f"{cubby}_{SESSION_STRING}.mkv"
    )

    csv_filename = os.path.join(
        SAVE_DIR,
        f"{cubby}_{SESSION_STRING}_frames.csv"
    )

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")

    writer = cv2.VideoWriter(
        video_filename,
        fourcc,
        FPS,
        (WIDTH, HEIGHT)
    )

    if not writer.isOpened():
        print(f"{cubby}: ERROR creating MKV")
        status[cubby] = "ERROR"
        connection.close()
        server.close()
        return

    csv_handle = open(csv_filename, "w", newline="")
    csv_writer = csv.writer(csv_handle)

    csv_writer.writerow([
        "frame",
        "time_seconds",
        "system_time"
    ])

    print(f"{cubby}: recording started")
    print(f"{cubby}: {video_filename}")

    data = b""
    header_size = struct.calcsize(">L")

    try:
        while recording:

            # Receive frame-size header.
            while len(data) < header_size and recording:
                try:
                    packet = connection.recv(4096)
                except socket.timeout:
                    continue

                if not packet:
                    raise ConnectionError("Camera disconnected")

                data += packet

            if not recording:
                break

            packed_size = data[:header_size]
            data = data[header_size:]
            frame_size = struct.unpack(">L", packed_size)[0]

            # Receive JPEG data.
            while len(data) < frame_size and recording:
                try:
                    packet = connection.recv(65536)
                except socket.timeout:
                    continue

                if not packet:
                    raise ConnectionError("Camera disconnected")

                data += packet

            if not recording:
                break

            frame_data = data[:frame_size]
            data = data[frame_size:]

            # Timestamp frame arrival on the desktop.
            frame_time = time.perf_counter() - session_start
            system_time = datetime.now().isoformat(timespec="microseconds")

            encoded = np.frombuffer(frame_data, dtype=np.uint8)
            frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

            if frame is None:
                print(f"{cubby}: bad frame")
                continue

            if frame.shape[1] != WIDTH or frame.shape[0] != HEIGHT:
                print(
                    f"{cubby}: unexpected frame size "
                    f"{frame.shape[1]}x{frame.shape[0]}"
                )
                continue

            writer.write(frame)

            frame_number = frame_counts[cubby]

            csv_writer.writerow([
                frame_number,
                f"{frame_time:.6f}",
                system_time
            ])

            frame_counts[cubby] += 1
            frames[cubby] = frame

    except (
        ConnectionError,
        ConnectionResetError,
        ConnectionAbortedError,
        BrokenPipeError,
        OSError
    ) as error:
        print(f"{cubby}: connection lost: {error}")
        status[cubby] = "DISCONNECTED"

    except Exception as error:
        print(f"{cubby}: error: {error}")
        status[cubby] = "ERROR"

    finally:
        writer.release()
        csv_handle.flush()
        csv_handle.close()

        try:
            connection.close()
        except Exception:
            pass

        try:
            server.close()
        except Exception:
            pass

        if status[cubby] == "RECORDING":
            status[cubby] = "STOPPED"

        print(f"{cubby}: {frame_counts[cubby]} frames saved")

# ============================================================
# START DESKTOP RECEIVERS
# ============================================================

threads = []

for cubby in ACTIVE_CUBBIES:
    info = CUBBIES[cubby]

    thread = threading.Thread(
        target=receive_camera,
        args=(cubby, info["port"]),
        daemon=True
    )

    thread.start()
    threads.append(thread)

time.sleep(0.5)

# ============================================================
# START CAMERA PROCESS ON EACH ACTIVE PI
# ============================================================

print()
print("Starting cameras...")
print()

for cubby in ACTIVE_CUBBIES:
    info = CUBBIES[cubby]

    try:
        command = [
            "ssh",
            "-o",
            "ConnectTimeout=3",
            f"{PI_USER}@{info['ip']}",
            (
                f"nohup python3 {PI_SCRIPT} "
                f"> {PI_LOG} 2>&1 &"
            )
        ]

        result = subprocess.run(
            command,
            timeout=5
        )

        if result.returncode == 0:
            print(f"{cubby}: start command sent")
        else:
            print(f"{cubby}: SSH start failed")
            status[cubby] = "SSH ERROR"

    except subprocess.TimeoutExpired:
        print(f"{cubby}: SSH timeout")
        status[cubby] = "SSH ERROR"

    except Exception as error:
        print(f"{cubby}: SSH error: {error}")
        status[cubby] = "SSH ERROR"

# ============================================================
# PREVIEW
# ============================================================

blank = np.zeros(
    (PREVIEW_HEIGHT, PREVIEW_WIDTH, 3),
    dtype=np.uint8
)

print()
print("========================================")
print(" RECORDING")
print("========================================")
print()
print("Press Q in the preview window to stop recording.")
print()

def make_preview(cubby):
    frame = frames[cubby]

    if frame is None:
        display = blank.copy()
    else:
        display = cv2.resize(
            frame,
            (PREVIEW_WIDTH, PREVIEW_HEIGHT)
        )

    cv2.putText(
        display,
        cubby,
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2
    )

    cv2.putText(
        display,
        status[cubby],
        (10, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (255, 255, 255),
        1
    )

    cv2.putText(
        display,
        f"Frames: {frame_counts[cubby]}",
        (10, 72),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (255, 255, 255),
        1
    )

    return display

try:
    while True:

        displays = [
            make_preview(cubby)
            for cubby in ACTIVE_CUBBIES
        ]

        number_of_cameras = len(displays)

        if number_of_cameras == 1:
            combined = displays[0]

        elif number_of_cameras == 2:
            combined = np.hstack(
                (displays[0], displays[1])
            )

        elif number_of_cameras == 3:
            top = np.hstack(
                (displays[0], displays[1])
            )

            empty_tile = blank.copy()

            bottom = np.hstack(
                (displays[2], empty_tile)
            )

            combined = np.vstack(
                (top, bottom)
            )

        else:
            top = np.hstack(
                (displays[0], displays[1])
            )

            bottom = np.hstack(
                (displays[2], displays[3])
            )

            combined = np.vstack(
                (top, bottom)
            )

        cv2.imshow(
            "Behavior Cameras",
            combined
        )

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            print()
            print("Stopping recordings...")
            break

except KeyboardInterrupt:
    print()
    print("Ctrl+C received.")
    print("Stopping recordings...")

# ============================================================
# STOP DESKTOP RECEIVERS
# ============================================================

recording = False

# ============================================================
# STOP CAMERA PROCESS ON EACH ACTIVE PI
# ============================================================

print()
print("Stopping Pi cameras...")
print()

for cubby in ACTIVE_CUBBIES:
    info = CUBBIES[cubby]

    try:
        command = [
            "ssh",
            "-o",
            "ConnectTimeout=2",
            f"{PI_USER}@{info['ip']}",
            "pkill -SIGTERM -f camera_stream.py"
        ]

        subprocess.run(
            command,
            timeout=4
        )

        print(f"{cubby}: stop command sent")

    except Exception:
        print(f"{cubby}: could not send stop command")

# ============================================================
# WAIT FOR RECEIVER THREADS
# ============================================================

for thread in threads:
    thread.join(timeout=3)

# ============================================================
# CLOSE PREVIEW
# ============================================================

cv2.destroyAllWindows()

# ============================================================
# FINAL SUMMARY
# ============================================================

print()
print("========================================")
print(" Recording complete")
print("========================================")
print()

for cubby in ACTIVE_CUBBIES:
    print(
        f"{cubby}: "
        f"{frame_counts[cubby]} frames "
        f"({status[cubby]})"
    )

print()
print("Files saved in:")
print(SAVE_DIR)
print()
