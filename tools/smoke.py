"""Exercise a real HTTP server with labeled synthetic data."""
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
def get(path):
    with urllib.request.urlopen(base + path, timeout=10) as response:
        return response.status, response.read()
for attempt in range(60):
    try:
        assert json.loads(get('/health')[1]) == {'status':'ok'}
        break
    except (OSError, AssertionError):
        if attempt == 59:
            raise
        time.sleep(.5)
assert b'<html' in get('/')[1].lower()
assert get('/docs')[0] == 200
schema = json.loads(get('/openapi.json')[1])
assert 'post' in schema['paths']['/analyze']
data = Path('examples/synthetic.json').read_bytes()
durations = []
for _ in range(3):
    start = time.perf_counter()
    request = urllib.request.Request(base + '/analyze', data=data, headers={'content-type':'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read())
        assert response.status == 200 and isinstance(result, dict) and result
    durations.append((time.perf_counter()-start)*1000)
request = urllib.request.Request(base+'/analyze', data=b'[]', headers={'content-type':'application/json'})
try:
    urllib.request.urlopen(request, timeout=10)
    raise RuntimeError('invalid input was accepted')
except urllib.error.HTTPError as error:
    assert error.code == 422
print(json.dumps({'synthetic':True,'http_status':200,'invalid_input_status':422,'latency_ms':durations,'result':result}, indent=2))
