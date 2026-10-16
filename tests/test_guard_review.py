"""Independent ASGI middleware tests without in-process HTTP client assumptions."""
import asyncio
import json
from app.guard import InputGuard


def invoke(scope, messages, downstream):
    output = []
    pending = iter(messages)
    async def receive():
        return next(pending)
    async def send(message):
        output.append(message)
    asyncio.run(InputGuard(downstream)(scope, receive, send))
    return output


def test_chunked_oversize_is_stopped_before_application():
    called=[]
    async def downstream(scope, receive, send):
        called.append(True)
    output=invoke({'type':'http','method':'POST'},[
        {'type':'http.request','body':b'a'*1048576,'more_body':True},
        {'type':'http.request','body':b'b'*1048577,'more_body':True},
    ], downstream)
    assert output[0]['status']==413
    assert not called


def test_chunked_json_is_replayed_as_complete_body():
    captured=[]
    async def downstream(scope, receive, send):
        message=await receive()
        captured.append(message)
    invoke({'type':'http','method':'PATCH'},[
        {'type':'http.request','body':b'{"x":','more_body':True},
        {'type':'http.request','body':b'1}','more_body':False},
    ],downstream)
    assert captured==[{'type':'http.request','body':b'{"x":1}','more_body':False}]


def test_disconnect_ends_without_application_or_response():
    called=[]
    async def downstream(scope, receive, send):
        called.append(True)
    output=invoke({'type':'http','method':'POST'},[
        {'type':'http.request','body':b'{','more_body':True},
        {'type':'http.disconnect'},
    ], downstream)
    assert output==[]
    assert called==[]


def test_get_and_non_http_scopes_bypass_body_read():
    captured=[]
    async def downstream(scope, receive, send):
        captured.append(scope)
    for scope in [{'type':'http','method':'GET'},{'type':'lifespan'},{'type':'websocket'}]:
        invoke(scope,[],downstream)
    assert len(captured)==3


def test_numeric_magnitude_and_invalid_encoding_rejected():
    async def downstream(scope, receive, send):
        raise AssertionError('Unsafe body reached application')
    for payload in [b'{"n":1e101}',b'{"n":'+b'9'*400+b'}',b'{"s":"\xff"}']:
        output=invoke({'type':'http','method':'PUT'},[{'type':'http.request','body':payload,'more_body':False}], downstream)
        assert output[0]['status']==422
        assert 'detail' in json.loads(output[1]['body'])
