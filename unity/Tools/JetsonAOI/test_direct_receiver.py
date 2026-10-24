"""Local WebSocket regression tests; never uses a real token or Jetson."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'FabSocket' / '.deps'))
import websockets

SCRIPT = Path(__file__).with_name('test-direct-aoi.ps1')
PHOTO = b'\xff\xd8\xff\xe0' + b'local-transfer-test' * 3000 + b'\xff\xd9'

async def check(case):
    async def serve(ws):
        request = json.loads(await ws.recv())
        response = dict(type='aoi.inspection.completed', schema_version=1,
                        request_id=request['request_id'], job_id=request['job_id'],
                        run_id=request['run_id'], lot_id=request['lot_id'],
                        unit_id=request['unit_id'], attempt=1, result_origin='mock',
                        binary_frame_follows=True,
                        image=dict(mime_type='image/jpeg', byte_length=len(PHOTO),
                                   sha256=hashlib.sha256(PHOTO).hexdigest(),
                                   file_name='../../unsafe.jpg'))
        if case == 'bad_hash':
            response['image']['sha256'] = '0' * 64
        if case == 'wrong_request':
            response['request_id'] = 'another-request'
        if case == 'nested_image_flag':
            response.pop('binary_frame_follows')
            response['image']['binary_frame_follows'] = True
        await ws.send(json.dumps(response))
        if case != 'missing_photo':
            try:
                await ws.send([PHOTO[:15000], PHOTO[15000:]])
            except websockets.ConnectionClosed:
                pass

    with tempfile.TemporaryDirectory(prefix='aoi-receiver-') as folder:
        root = Path(folder)
        async with websockets.serve(serve, '127.0.0.1', 0) as server:
            port = server.sockets[0].getsockname()[1]
            code = SCRIPT.read_text(encoding='utf-8-sig')
            code = code.replace("$endpoint = 'ws://192.168.213.167:8400/aoi'",
                                f"$endpoint = 'ws://127.0.0.1:{port}/aoi'")
            temporary_script = root / 'receiver.ps1'
            temporary_script.write_text(code, encoding='utf-8-sig')
            command = ("function global:Read-Host { param($Prompt,[switch]$AsSecureString) "
                       "if ($AsSecureString) { $s=New-Object Security.SecureString; 'local-test-token'.ToCharArray() | ForEach-Object { $s.AppendChar($_) }; $s } "
                       "else { '' } }; & '" + str(temporary_script).replace("'", "''") + "'")
            process = await asyncio.create_subprocess_exec(
                'powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(process.communicate(), 20)
        reports = list((root / 'DirectTestResults').glob('*.json'))
        assert len(reports) == 1, (stdout, stderr)
        report = json.loads(reports[0].read_text(encoding='utf-8-sig'))
        photos = list((root / 'DirectTestResults').glob('*.jpg'))
        if case in ('success', 'nested_image_flag'):
            assert report['status'] == 'result_and_image_received', report
            assert len(photos) == 1 and photos[0].read_bytes() == PHOTO, report
        else:
            assert report['status'] == 'failed' and not photos, report
        assert 'local-test-token' not in reports[0].read_text(encoding='utf-8-sig')
        print('PASS:', case)

async def main():
    for case in ('nested_image_flag', 'success', 'bad_hash', 'missing_photo', 'wrong_request'):
        await check(case)

if __name__ == '__main__':
    asyncio.run(main())
