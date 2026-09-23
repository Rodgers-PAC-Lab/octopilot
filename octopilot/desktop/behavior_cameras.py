import socket
import struct
import subprocess
import threading
import os
import csv
import time
from datetime import datetime

CUBBIES = {
    "cubbyA": {"hostname": "rpi27", "ip": "192.168.0.127", "port": 6027},
    "cubbyB": {"hostname": "rpi29", "ip": "192.168.0.129", "port": 6029},
    "cubbyC": {"hostname": "rpi33", "ip": "192.168.0.133", "port": 6033},
    "cubbyD": {"hostname": "rpi34", "ip": "192.168.0.134", "port": 6034},
}

# Useful for testing individual board's cameras (otherwise add all boards)
ACTIVE_CUBBIES = ["cubbyA", "cubbyC"]

PI_USER = "pi"
PI_SCRIPT = "/home/pi/dev/octopilot/octopilot/pi/camera_stream.py"
PI_LOG = "/home/pi/camera.log"

WIDTH = 800
HEIGHT = 600
FPS = 15
PREVIEW_WIDTH = 320
PREVIEW_HEIGHT = 240

for cubby in ACTIVE_CUBBIES:
    if cubby not in CUBBIES:
        raise ValueError(f"Unknown cubby: {cubby}")
if not ACTIVE_CUBBIES:
    raise ValueError("ACTIVE_CUBBIES cannot be empty.")

now = datetime.now()
DATE_STRING = now.strftime("%Y%m%d")
SESSION_STRING = now.strftime("%Y%m%d_%H%M%S")
SAVE_DIR = f"/home/mouse/Videos/{DATE_STRING}_behavior_videos"
os.makedirs(SAVE_DIR, exist_ok=True)

print("\n========================================")
print(" Behavior Camera System")
print("========================================")
print(f"\nSession: {SESSION_STRING}\n\nActive cubbies:")
for cubby in ACTIVE_CUBBIES:
    info = CUBBIES[cubby]
    print(f"  {cubby}: {info['hostname']} ({info['ip']})")
print(f"\nSaving videos to:\n{SAVE_DIR}\n")

# Open all listening sockets BEFORE starting the Pis.
servers = {}
for cubby in ACTIVE_CUBBIES:
    port = CUBBIES[cubby]["port"]
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.settimeout(1.0)
    server.bind(("0.0.0.0", port))
    server.listen(1)
    servers[cubby] = server
    print(f"{cubby}: waiting on port {port}")

# IMPORTANT: start all Pi camera processes BEFORE importing cv2.
# On Shark, cv2 loads OpenSSL 3.6.x. /usr/bin/ssh expects OpenSSL 3.0.x,
# so SSH must be finished before cv2 is loaded into this Python process.
print("\nStarting cameras...\n")
start_success = {}

for cubby in ACTIVE_CUBBIES:
    info = CUBBIES[cubby]
    command = [
        "/usr/bin/ssh",
        "-o", "ConnectTimeout=3",
        f"{PI_USER}@{info['ip']}",
        f"nohup python3 {PI_SCRIPT} > {PI_LOG} 2>&1 &",
    ]
    try:
        result = subprocess.run(command, timeout=5)
        start_success[cubby] = result.returncode == 0
        print(f"{cubby}: " + ("start command sent" if result.returncode == 0 else "SSH start failed"))
    except subprocess.TimeoutExpired:
        start_success[cubby] = False
        print(f"{cubby}: SSH timeout")
    except Exception as error:
        start_success[cubby] = False
        print(f"{cubby}: SSH error: {error}")

# Only now load OpenCV/Numpy.
import cv2
import numpy as np

frames = {cubby: None for cubby in ACTIVE_CUBBIES}
status = {
    cubby: ("WAITING" if start_success.get(cubby, False) else "SSH ERROR")
    for cubby in ACTIVE_CUBBIES
}
frame_counts = {cubby: 0 for cubby in ACTIVE_CUBBIES}
connections = {cubby: None for cubby in ACTIVE_CUBBIES}
recording = True
session_start = time.perf_counter()

def receive_camera(cubby):
    global recording
    server = servers[cubby]
    connection = None

    while recording:
        try:
            connection, address = server.accept()
            connections[cubby] = connection
            break
        except socket.timeout:
            continue
        except OSError:
            return
        except Exception as error:
            if recording:
                print(f"{cubby}: connection error: {error}")
                status[cubby] = "ERROR"
            return

    if connection is None:
        return

    connection.settimeout(2.0)
    print(f"{cubby}: connected from {address[0]}")
    status[cubby] = "RECORDING"

    video_filename = os.path.join(SAVE_DIR, f"{cubby}_{SESSION_STRING}.mkv")
    csv_filename = os.path.join(SAVE_DIR, f"{cubby}_{SESSION_STRING}_frames.csv")

    writer = cv2.VideoWriter(
        video_filename,
        cv2.VideoWriter_fourcc(*"MJPG"),
        FPS,
        (WIDTH, HEIGHT),
    )

    if not writer.isOpened():
        print(f"{cubby}: ERROR creating MKV")
        status[cubby] = "ERROR"
        connection.close()
        return

    csv_handle = open(csv_filename, "w", newline="")
    csv_writer = csv.writer(csv_handle)
    csv_writer.writerow(["frame", "time_seconds", "system_time"])

    print(f"{cubby}: recording started")
    print(f"{cubby}: {video_filename}")

    data = b""
    header_size = struct.calcsize(">L")

    try:
        while recording:
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

            frame_size = struct.unpack(">L", data[:header_size])[0]
            data = data[header_size:]

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

            frame_time = time.perf_counter() - session_start
            system_time = datetime.now().isoformat(timespec="microseconds")

            encoded = np.frombuffer(frame_data, dtype=np.uint8)
            frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

            if frame is None:
                continue

            if frame.shape[1] != WIDTH or frame.shape[0] != HEIGHT:
                print(f"{cubby}: unexpected frame size {frame.shape[1]}x{frame.shape[0]}")
                continue

            writer.write(frame)

            frame_number = frame_counts[cubby]
            csv_writer.writerow([frame_number, f"{frame_time:.6f}", system_time])
            frame_counts[cubby] += 1
            frames[cubby] = frame

    except (ConnectionError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError) as error:
        if recording:
            print(f"{cubby}: connection lost: {error}")
            status[cubby] = "DISCONNECTED"
    except Exception as error:
        if recording:
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
        connections[cubby] = None
        if status[cubby] == "RECORDING":
            status[cubby] = "STOPPED"
        print(f"{cubby}: {frame_counts[cubby]} frames saved")

threads = []
for cubby in ACTIVE_CUBBIES:
    thread = threading.Thread(target=receive_camera, args=(cubby,), daemon=True)
    thread.start()
    threads.append(thread)

blank = np.zeros((PREVIEW_HEIGHT, PREVIEW_WIDTH, 3), dtype=np.uint8)

def make_preview(cubby):
    frame = frames[cubby]
    if frame is None:
        display = blank.copy()
    else:
        display = cv2.resize(frame, (PREVIEW_WIDTH, PREVIEW_HEIGHT))

    cv2.putText(display, cubby, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    cv2.putText(display, status[cubby], (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    cv2.putText(display, f"Frames: {frame_counts[cubby]}", (10, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    return display

print("\n========================================")
print(" RECORDING")
print("========================================")
print("\nPress Q in the preview window to stop recording.\n")

try:
    while True:
        displays = [make_preview(cubby) for cubby in ACTIVE_CUBBIES]
        n = len(displays)

        if n == 1:
            combined = displays[0]
        elif n == 2:
            combined = np.hstack((displays[0], displays[1]))
        elif n == 3:
            combined = np.vstack((
                np.hstack((displays[0], displays[1])),
                np.hstack((displays[2], blank.copy())),
            ))
        else:
            combined = np.vstack((
                np.hstack((displays[0], displays[1])),
                np.hstack((displays[2], displays[3])),
            ))

        cv2.imshow("Behavior Cameras", combined)
        if (cv2.waitKey(1) & 0xFF) == ord("q"):
            print("\nStopping recordings...")
            break
except KeyboardInterrupt:
    print("\nCtrl+C received. Stopping recordings...")

# Do not use SSH here because cv2 is already loaded.
# Close active TCP connections instead. The Pi script sees the broken
# connection, exits its send loop, releases /dev/video0, and terminates.
recording = False

for connection in list(connections.values()):
    if connection is not None:
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            connection.close()
        except Exception:
            pass

for server in servers.values():
    try:
        server.close()
    except Exception:
        pass

for thread in threads:
    thread.join(timeout=4)

cv2.destroyAllWindows()

print("\n========================================")
print(" Recording complete")
print("========================================\n")
for cubby in ACTIVE_CUBBIES:
    print(f"{cubby}: {frame_counts[cubby]} frames ({status[cubby]})")
print(f"\nFiles saved in:\n{SAVE_DIR}\n")
