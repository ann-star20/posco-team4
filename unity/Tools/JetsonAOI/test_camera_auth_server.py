"""Local-only Digest fixture; uses dummy credentials, never phone credentials."""
import hashlib
import pathlib
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

md5 = lambda value: hashlib.md5(value.encode()).hexdigest()
class Handler(BaseHTTPRequestHandler):
    basic_leak = False
    def log_message(self, *_): pass
    def do_GET(self):
        auth = self.headers.get('Authorization', '')
        if self.path == '/redirect':
            self.send_response(302); self.send_header('Location', '/video'); self.send_header('Content-Length', '0'); self.end_headers(); return
        if self.path == '/basic':
            Handler.basic_leak |= bool(auth)
            self.send_response(401); self.send_header('WWW-Authenticate', 'Basic realm="camera-test"'); self.send_header('Content-Length', '0'); self.end_headers(); return
        fields = {}
        for key, quoted, plain in re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]+))', auth): fields[key] = quoted or plain
        valid = False
        if auth.startswith('Digest ') and fields.get('qop') == 'auth':
            expected = md5(':'.join([md5('test-camera-user:camera-test:test-camera-password'), 'test-nonce', fields.get('nc',''), fields.get('cnonce',''), 'auth', md5('GET:/video')]))
            valid = fields.get('response') == expected and fields.get('uri') == '/video'
        self.send_response(200 if valid else 401)
        if not valid: self.send_header('WWW-Authenticate', 'Digest realm="camera-test", nonce="test-nonce", qop="auth", algorithm=MD5')
        self.send_header('Content-Length', '0'); self.end_headers()

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    script = pathlib.Path(__file__).with_name('test-camera-auth.ps1')
    result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script), '-Port', str(server.server_port)], timeout=45)
    if result.returncode: raise SystemExit(result.returncode)
    assert not Handler.basic_leak, 'Basic Authorization was transmitted'
    print('PASS: local server verified no Basic credential transmission')
finally:
    server.shutdown(); server.server_close()
