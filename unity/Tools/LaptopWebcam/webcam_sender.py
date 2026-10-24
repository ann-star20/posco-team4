"""Windows webcam -> MJPEG for the existing Jetson camera source."""
import sys


def check_progress(message):
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        with open(sys.argv[2] + '.progress', 'w', encoding='utf-8') as report:
            report.write(message)


check_progress('Loading standard libraries')
import json
import queue
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

check_progress('Loading OpenCV')
import cv2
check_progress('OpenCV loaded')


class Frames:
    def __init__(self):
        self.condition = threading.Condition()
        self.jpeg = None
        self.sequence = 0
        self.running = True
        self.clients = 0

    def publish(self, jpeg):
        with self.condition:
            self.jpeg = jpeg
            self.sequence += 1
            self.condition.notify_all()

    def stop(self):
        with self.condition:
            self.running = False
            self.condition.notify_all()


def make_server(frames, host="0.0.0.0", port=8080):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/video":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                with frames.condition:
                    frames.clients += 1
                sequence = -1
                try:
                    while frames.running:
                        with frames.condition:
                            frames.condition.wait_for(
                                lambda: not frames.running or frames.sequence != sequence, 2)
                            if not frames.running:
                                break
                            jpeg, sequence = frames.jpeg, frames.sequence
                        if jpeg is None:
                            continue
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
                    pass
                finally:
                    with frames.condition:
                        frames.clients -= 1
                return
            if path == "/health":
                with frames.condition:
                    body = json.dumps({"running": frames.running, "frames": frames.sequence,
                                       "subscribers": frames.clients}).encode()
                content_type = "application/json"
            elif path in ("/shot.jpg", "/photo.jpg"):
                with frames.condition:
                    body = frames.jpeg
                if body is None:
                    self.send_error(503, "Camera frame unavailable")
                    return
                content_type = "image/jpeg"
            elif path == "/":
                body = b'<!doctype html><title>AOI Webcam</title><body style="background:#111;color:white;font-family:sans-serif"><h2>AOI Webcam - LIVE</h2><img style="max-width:100%" src="/video"></body>'
                content_type = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def lan_addresses():
    addresses = set()
    for host in ("192.168.213.167", "192.168.212.10"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
                connection.connect((host, 9))  # Route lookup only; sends no packet.
                addresses.add(connection.getsockname()[0])
        except OSError:
            pass
    try:
        addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return sorted(ip for ip in addresses if not ip.startswith(("127.", "169.254.")))


def main(smoke=False):
    import os
    previous_directory = os.getcwd()
    if getattr(sys, 'frozen', False):
        # Relative resource paths also work when Windows expands user-folder aliases.
        os.chdir(sys._MEIPASS)
        os.environ['TCL_LIBRARY'] = '_tcl_data'
        os.environ['TK_LIBRARY'] = '_tk_data'
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    if smoke:
        root.withdraw()
    root.title("AOI 노트북 웹캠 송출")
    root.geometry("710x420")
    root.resizable(False, False)
    panel = ttk.Frame(root, padding=22)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="AOI 노트북 웹캠 송출", font=("맑은 고딕", 19, "bold")).pack(anchor="w")
    ttk.Label(panel, text="이 노트북에서 실행 · 영상은 Jetson에서 검사하고 Unity에 표시됩니다.").pack(anchor="w", pady=(6, 16))
    row = ttk.Frame(panel)
    row.pack(fill="x")
    ttk.Label(row, text="카메라 번호").pack(side="left")
    camera = ttk.Combobox(row, values=[0, 1, 2, 3], state="readonly", width=5)
    camera.set(0)
    camera.pack(side="left", padx=10)
    ttk.Label(row, text="기본 0 · 외장 웹캠이면 1도 확인").pack(side="left")
    addresses = lan_addresses()
    ttk.Label(panel, text="Jetson 연결에 사용할 영상 주소 (Wi-Fi / 유선 IP)").pack(anchor="w", pady=(16, 4))
    url = ttk.Combobox(panel, values=[f"http://{ip}:8080/video" for ip in addresses], width=75)
    url.set(f"http://{addresses[0]}:8080/video" if addresses else "http://노트북_IP:8080/video")
    url.pack(fill="x")
    status = tk.StringVar(value="송출 시작을 누르세요.")
    ttk.Label(panel, textvariable=status, wraplength=660).pack(anchor="w", pady=15)
    messages = queue.Queue()
    session = {"frames": None, "server": None, "thread": None}

    def capture(index, frames):
        cap = None
        try:
            for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
                cap = cv2.VideoCapture(index, backend)
                if cap.isOpened():
                    break
                cap.release()
            if not cap.isOpened():
                raise RuntimeError("웹캠을 열 수 없습니다. 카메라 번호와 Windows 카메라 권한을 확인하세요.")
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 15)
            failures = 0
            while frames.running:
                started = time.monotonic()
                ok, image = cap.read()
                if not ok:
                    failures += 1
                    if failures >= 30:
                        raise RuntimeError("웹캠 영상이 끊겼습니다. 다른 카메라 앱을 닫고 다시 시작하세요.")
                    time.sleep(0.1)
                    continue
                failures = 0
                ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
                if not ok:
                    raise RuntimeError("웹캠 영상 변환에 실패했습니다.")
                frames.publish(encoded.tobytes())
                time.sleep(max(0, 1 / 15 - (time.monotonic() - started)))
        except Exception as error:
            frames.stop()
            messages.put(str(error))
        finally:
            if cap is not None:
                cap.release()

    def stop():
        frames = session["frames"]
        if frames:
            frames.stop()
        server = session["server"]
        if server:
            server.shutdown()
            server.server_close()
        worker = session["thread"]
        if worker:
            worker.join(timeout=1)
        session.update(frames=None, server=None, thread=None)
        start_button.configure(state="normal")
        camera.configure(state="readonly")
        status.set("송출 중지됨")

    def start():
        frames = Frames()
        try:
            server = make_server(frames)
        except OSError as error:
            messagebox.showerror("송출 시작 실패", f"8080 포트를 열 수 없습니다. 이미 실행 중인 송출 창이 있는지 확인하세요.\n{error}")
            return
        worker = threading.Thread(target=capture, args=(int(camera.get()), frames), daemon=True)
        session.update(frames=frames, server=server, thread=worker)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        worker.start()
        start_button.configure(state="disabled")
        camera.configure(state="disabled")
        status.set("웹캠 연결 중...")

    def copy():
        root.clipboard_clear()
        root.clipboard_append(url.get())
        root.update()

    buttons = ttk.Frame(panel)
    buttons.pack(fill="x")
    start_button = ttk.Button(buttons, text="송출 시작", command=start)
    start_button.pack(side="left")
    ttk.Button(buttons, text="영상 미리보기", command=lambda: webbrowser.open("http://127.0.0.1:8080/")).pack(side="left", padx=8)
    ttk.Button(buttons, text="주소 복사", command=copy).pack(side="left")
    ttk.Button(buttons, text="송출 중지", command=stop).pack(side="right")
    ttk.Label(panel, text="방화벽 알림이 뜨면 사용하는 사설 네트워크에서 허용하세요.\n인증 없는 내부망 영상 송출입니다. 신뢰하는 네트워크에서만 사용하세요.\nJetson에 연결한 뒤에도 이 창은 계속 열어두세요.", wraplength=660).pack(anchor="w", pady=16)

    def update():
        try:
            error = messages.get_nowait()
        except queue.Empty:
            error = None
        if error:
            stop()
            status.set(error)
        frames = session["frames"]
        if frames and frames.running and frames.sequence:
            status.set(f"송출 중 · 촬영 {frames.sequence} 프레임 · 영상 연결 {frames.clients}개 · 최대 1280×720 / 15 fps")
        root.after(500, update)

    def close():
        stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    update()
    if smoke:
        root.after(0, close)
    root.mainloop()
    os.chdir(previous_directory)


def self_test(path):
    """Exercise the actual HTTP/JPEG path with an explicit synthetic frame."""
    check_progress('Starting HTTP self-test')
    from http.client import HTTPConnection
    import numpy as np
    frames = Frames()
    ok, jpeg = cv2.imencode(".jpg", np.full((240, 320, 3), 100, dtype=np.uint8))
    assert ok
    frames.publish(jpeg.tobytes())
    server = make_server(frames, "127.0.0.1", 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    def get(path):
        connection = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        connection.request('GET', path)
        return connection, connection.getresponse()

    try:
        connection, response = get('/health')
        try:
            assert json.loads(response.read())["frames"] == 1
        finally:
            connection.close()
        connection, response = get('/shot.jpg')
        try:
            image = cv2.imdecode(np.frombuffer(response.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
            assert image.shape == (240, 320, 3)
        finally:
            connection.close()
        connection, response = get('/video')
        try:
            assert "boundary=frame" in response.headers["Content-Type"]
            assert response.readline() == b"--frame\r\n"
            assert response.readline() == b"Content-Type: image/jpeg\r\n"
            length = int(response.readline().split(b":")[1])
            assert response.readline() == b"\r\n"
            assert response.read(length) == jpeg.tobytes()
        finally:
            response.close()
            connection.close()
        result = "PASS: HTTP health, snapshot JPEG decode, MJPEG multipart and GUI creation. Synthetic frame only; webcam hardware not tested."
    finally:
        frames.stop()
        server.shutdown()
        server.server_close()
    check_progress('Creating GUI')
    main(smoke=True)
    from pathlib import Path
    Path(path).write_text(result, encoding="utf-8")
    check_progress('Complete')


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        self_test(sys.argv[2])
    else:
        main()
