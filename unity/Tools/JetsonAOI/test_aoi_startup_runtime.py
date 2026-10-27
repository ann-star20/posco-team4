import ast
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
import base64
import shlex
import sys
from urllib.parse import urlsplit,urlunsplit
from ipaddress import IPv4Address

shell=Path(__file__).with_name('start_aoi_existing.sh').read_text()
body=shell.split("<<'PY'\n",1)[1].rsplit('\nPY',1)[0]
tree=ast.parse(body)
parts=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('select_python','camera_url_for_host','is_existing_aoi','same_aoi_instance','process_start_stamp') or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='check' for t in n.targets)]
scope={'subprocess':subprocess,'urlsplit':urlsplit,'urlunsplit':urlunsplit,'IPv4Address':IPv4Address,'base':Path('/expected/aoi'),'os':types.SimpleNamespace(getuid=lambda:1000)}
exec(compile(ast.Module(body=parts,type_ignores=[]),'startup-selection','exec'),scope)

class RuntimeChecks(unittest.TestCase):
    def test_laptop_source_overrides_phone_path_and_credentials_for_session(self):
        change=next(n for n in tree.body if isinstance(n,ast.Try) and any(isinstance(x,ast.If) and 'AOI_LAPTOP_CAMERA_HOST' in ast.unparse(x.test) for x in n.body))
        with patch.dict(os.environ,{'AOI_LAPTOP_CAMERA_HOST':'192.168.213.99','CAMERA_SOURCE_URL':'rtsp://user:example@192.168.10.123/old-path'}):
            with redirect_stdout(io.StringIO()):
                exec(compile(ast.Module(body=change.body,type_ignores=[]),'laptop-source','exec'),{'os':os,'IPv4Address':IPv4Address})
            self.assertEqual(os.environ['CAMERA_SOURCE_URL'],'http://192.168.213.99:8080/video')
    def test_force_stop_rejects_reused_pid(self):
        args=['python','-m','fab_virtual_lot.aoi_unity'];cwd=scope['base'].resolve()
        self.assertTrue(scope['same_aoi_instance'](args,cwd,1000,'123','123'))
        self.assertFalse(scope['same_aoi_instance'](args,cwd,1000,'456','123'))
        self.assertFalse(scope['same_aoi_instance'](args,cwd,2000,'123','123'))
        self.assertFalse(scope['same_aoi_instance'](['python','other'],cwd,1000,'123','123'))
    def test_proc_stamp_handles_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);path.joinpath('stat').write_text('123 (aoi process (worker)) '+' '.join(str(n) for n in range(3,30)))
            self.assertEqual(scope['process_start_stamp'](path),'22')
    def test_restart_rejects_unrelated_process(self):
        guard=scope['is_existing_aoi'];cwd=scope['base'].resolve()
        args=['python','-u','-m','fab_virtual_lot.aoi_unity']
        self.assertTrue(guard(args,cwd,1000))
        self.assertFalse(guard(args,cwd,2000))
        self.assertFalse(guard(args,Path('/different'),1000))
        self.assertFalse(guard(['python','-m','other_service'],cwd,1000))
    def test_remote_bootstrap_forwards_bash_as_arguments(self):
        launcher=Path(__file__).with_name('Start-Aoi8500And8400.ps1').read_text(encoding='utf-8-sig')
        line=next(v for v in launcher.splitlines() if v.startswith('$remote='))
        payload=b'printf ready\n'
        command=line[len('$remote="'):-1].replace('$encoded',base64.b64encode(payload).decode())
        args=shlex.split(command)
        self.assertEqual(args[-2:],['bash','-s'])
        with patch.object(sys,'argv',args[2:]),patch('subprocess.run',return_value=types.SimpleNamespace(returncode=0)) as run:
            with self.assertRaises(SystemExit) as result:exec(args[2],{})
            self.assertEqual(result.exception.code,0)
            run.assert_called_once_with(['bash','-s'],input=payload)
    def test_source_transport_does_not_use_text_pipeline(self):
        launcher=Path(__file__).with_name('Start-Aoi8500And8400.ps1').read_text(encoding='utf-8-sig')
        self.assertNotIn('$body |',launcher)
        self.assertIn('input=base64.b64decode(sys.argv[1])',launcher)
        self.assertIn('.Replace("`r","")',launcher)
        remote=next(line for line in launcher.splitlines() if line.startswith('$remote='))
        self.assertNotIn('[""bash',remote)
        self.assertIn('subprocess.run(sys.argv[2:]',remote)
        self.assertIn('$encoded bash -s',remote)
    def test_camera_host_preserves_credentials_and_path(self):
        result=scope['camera_url_for_host']('http://operator:example@192.168.10.111:8080/video?mode=mjpeg','192.168.10.123')
        self.assertEqual(result,'http://operator:example@192.168.10.123:8080/video?mode=mjpeg')
        self.assertIn('export AOI_CAMERA_HOST_OVERRIDE=192.168.10.123',shell)
    def test_readiness_does_not_open_websocket(self):
        self.assertNotIn("socket.create_connection",body)
        self.assertIn("ss','-H','-ltn",body)
    def test_explicit_abi_imports(self):
        for required in ('import matplotlib.transforms','import matplotlib._path','torch.from_numpy','from fab_virtual_lot.aoi_worker import make_models'):
            self.assertIn(required,scope['check'])
    def test_skip_incompatible_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            first=Path(folder)/'incompatible';second=Path(folder)/'compatible'
            first.touch();second.touch();calls=[]
            def runner(args,**kwargs):
                calls.append(args[0]);return types.SimpleNamespace(returncode=1 if args[0]==str(first) else 0)
            with redirect_stdout(io.StringIO()):result=scope['select_python']([first,first,second],runner)
            self.assertEqual(result,str(second));self.assertEqual(calls,[str(first),str(second)])
    def test_no_compatible_runtime(self):
        with tempfile.NamedTemporaryFile() as file:
            with redirect_stdout(io.StringIO()):
                self.assertIsNone(scope['select_python']([Path(file.name)],lambda *a,**k:types.SimpleNamespace(returncode=1)))

if __name__=='__main__':unittest.main()
