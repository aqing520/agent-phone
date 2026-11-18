"""Isolated DeepSeek image validation, durable jobs, and history tests."""
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dsh_images import validate_images
from control import ControlService, ControlError
import server

PNG = base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
IMAGE = {'mimeType':'image/png', 'data':PNG}

class ImageTests(unittest.TestCase):
    def test_validation(self):
        self.assertEqual(validate_images([IMAGE])[0]['type'], 'image')
        for images in ([{'mimeType':'image/jpeg','data':PNG}], [dict(IMAGE,data='not base64')], [IMAGE]*5, 'bad'):
            with self.subTest(images=images), self.assertRaises(ValueError): validate_images(images)

    def test_durable_image_only_job_and_idempotency(self):
        with tempfile.TemporaryDirectory() as root:
            service=ControlService(Path(root)/'jobs.sqlite', dsh='fake')
            payload={'source':'dsh','session':str(uuid.uuid4()),'requestId':str(uuid.uuid4()),'text':'','images':[IMAGE]}
            with patch.object(service, 'capabilities', return_value={'dsh': {'available': True, 'runtime': {}}}):
                with self.assertRaises(ControlError) as rejected:
                    service.submit(payload, lambda *_: root)
                self.assertEqual(rejected.exception.code, 'image_unavailable')
            with patch.object(service, 'runtime_call', return_value={'ready': True, 'imageInput': True}):
                a=service.submit(payload,lambda *_:root)
                b=service.submit(payload,lambda *_:root)
                self.assertEqual(a['id'],b['id'])
                with service.db() as db:
                    row=db.execute('SELECT images FROM jobs').fetchone()
                    self.assertEqual(json.loads(row['images'])[0]['data'],PNG)
                with self.assertRaises(ControlError):
                    service.submit(dict(payload,text='changed'),lambda *_:root)

    def test_image_only_history_not_dropped(self):
        event={'type':'user/message','data':{'source':{'kind':'user'},'content':[dict(IMAGE,type='image')]}}
        with patch.object(server,'_dsh_events',return_value=[event]):
            rows=server.parse_dsh_messages('test')
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['images'][0]['data'], PNG)

    def test_normalized_attachment_requires_matching_digest(self):
        raw = base64.b64decode(PNG)
        digest = hashlib.sha256(raw).hexdigest()
        block = {'type': 'image', 'attachment': {'attachmentId': f'sha256:{digest}', 'mediaType': 'image/png'}}
        with tempfile.TemporaryDirectory() as root, patch.object(server, 'DSH', root):
            path = Path(root) / 'attachments' / 'v1' / 'objects' / digest[:2] / digest
            path.parent.mkdir(parents=True)
            path.write_bytes(raw)
            self.assertEqual(server.dsh_content_images([block]), [IMAGE])
            path.write_bytes(raw + b'corrupt')
            self.assertEqual(server.dsh_content_images([block]), [])
            self.assertEqual(server.dsh_content_images([dict(block, attachment='bad')]), [])

if __name__=='__main__': unittest.main()
