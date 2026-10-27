import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

import cv2
import numpy as np

from webcam_sender import Frames, make_server, self_test


class SenderTests(unittest.TestCase):
    def test_http_jpeg_multipart_self_check(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'result.txt'
            self_test(output)
            self.assertTrue(output.read_text().startswith('PASS:'))

    def test_jetson_style_opencv_mjpeg_reader(self):
        frames = Frames()
        ok, jpeg = cv2.imencode('.jpg', np.full((240, 320, 3), 80, dtype=np.uint8))
        self.assertTrue(ok)
        server = make_server(frames, '127.0.0.1', 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()

        def publish():
            while frames.running:
                frames.publish(jpeg.tobytes())
                time.sleep(0.05)

        threading.Thread(target=publish, daemon=True).start()
        camera = None
        try:
            camera = cv2.VideoCapture(f'http://127.0.0.1:{server.server_port}/video', cv2.CAP_FFMPEG,
                                      [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000])
            self.assertTrue(camera.isOpened())
            ok, image = camera.read()
            self.assertTrue(ok)
            self.assertEqual(image.shape, (240, 320, 3))
        finally:
            if camera:
                camera.release()
            frames.stop()
            server.shutdown()
            server.server_close()

    def test_no_frame_is_not_a_fake_snapshot(self):
        frames = Frames()
        server = make_server(frames, '127.0.0.1', 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(base + '/shot.jpg', timeout=3)
            self.assertEqual(error.exception.code, 503)
            with urllib.request.urlopen(base + '/health', timeout=3) as response:
                self.assertEqual(json.load(response)['frames'], 0)
        finally:
            frames.stop()
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
