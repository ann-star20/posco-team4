"""One-use loopback bootstrap: keep the Gateway credential in process memory only."""
import http.server
import json
import os
import pathlib
import uuid

root = pathlib.Path(__file__).resolve().parents[2]
token = os.environ['UNITY_GATEWAY_TOKEN']
selected = None
for path in sorted((root / 'Tools/Gateway/Requests').glob('*.events.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True):
    events = path.read_text(encoding='utf-8-sig').splitlines()
    if any(json.loads(line).get('event_type') == 'tcad.verification.review_required' for line in events):
        selected = (path, events)
        break
if selected is None:
    raise RuntimeError('No received review_required event exists')
path, events = selected
request = path.with_name(path.name.replace('.events.jsonl', '.json')).read_text(encoding='utf-8-sig')
payload = json.dumps(dict(token=token, endpoint='ws://192.168.212.10:8000/api/v1/stream', request_json=request, events=events), ensure_ascii=False).encode('utf-8')
nonce = '/' + uuid.uuid4().hex

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != nonce:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *args):
        pass

server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
server.timeout = 240
(root / 'GatewayApprovalWindowCheck.once').write_text('http://127.0.0.1:%d%s' % (server.server_port, nonce), encoding='utf-8')
print('WINDOW_CHECK_BOOTSTRAP_READY: ' + path.name, flush=True)
server.handle_request()
server.server_close()
print('WINDOW_CHECK_BOOTSTRAP_CLOSED', flush=True)
