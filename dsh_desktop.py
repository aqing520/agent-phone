"""Bounded RPC to the bridge hosted by DeepSeek Desktop, never a second owner."""
import json
import socket
from pathlib import Path


def desktop_call(method='status', session=None):
    path=Path.home()/'.config/agent-phone/control/dsh-desktop.sock'
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(5)
            client.connect(str(path))
            client.sendall((json.dumps({'method':method,'session':session})+'\n').encode())
            data=b''
            while b'\n' not in data and len(data)<1024*1024:
                chunk=client.recv(65536)
                if not chunk:break
                data+=chunk
            result=json.loads(data.split(b'\n')[0])
            return result if isinstance(result,dict) else {'ready':False}
    except (OSError,ValueError):
        return {'ready':False,'error':'DeepSeek 桌面桥接未连接，请安装插件并重启桌面 App。'}
