import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import datetime, timezone
from pixel_ops.data_sources.codex_status import CodexStatusSource
import websocket, json
original = websocket.create_connection
def connect(*args, **kwargs):
 w = original(*args, **kwargs)
 recv = w.recv
 def receive():
  raw = recv()
  r = json.loads(raw)
  t = r.get('result', {}).get('thread', {})
  print('RPC', r.get('id'), {k:t.get(k) for k in ('ephemeral', 'source', 'status')}, r.get('error'))
  return raw
 w.recv = receive
 return w
websocket.create_connection = connect
print(CodexStatusSource().current(datetime.now(timezone.utc)))
