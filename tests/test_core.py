from app.core import *

def test_actual_predictions_and_labels():
    req=BenchmarkRequest(cases=[Case(question='What color is the boat?',context='The bicycle is green. The boat is blue.',expected_answer='The boat is blue.')],repeats=2)
    r=analyze(req)['results']
    assert r[0]['exact_match_accuracy']==0
    assert r[1]['exact_match_accuracy']==1
    assert r[1]['predictions']==['The boat is blue.']
    assert all(x['measured_runs']==2 and x['mean_latency_ms']>=0 for x in r)

def test_tie_and_punctuation():
    c=Case(question='unknown?',context='One. Two.',expected_answer='ONE')
    assert predict(c,'lexical_retrieval')=='One.'
    assert analyze(BenchmarkRequest(cases=[c]))['results'][0]['exact_match_accuracy']==1

def test_empty_cases_rejected():
    import pytest
    with pytest.raises(ValueError): BenchmarkRequest(cases=[])


def test_local_adapter_success_with_mock(monkeypatch):
    import httpx
    from app import core
    original=httpx.Client
    def handle(request):
        import json
        payload=json.loads(request.content)
        assert payload['model']=='tiny'
        assert payload['max_tokens']==16
        return httpx.Response(200,json={'choices':[{'message':{'content':'Blue.'}}]})
    monkeypatch.setattr(core.httpx,'Client',lambda **kwargs: original(transport=httpx.MockTransport(handle),**kwargs))
    req=BenchmarkRequest(cases=[Case(question='Color?',context='Blue.',expected_answer='Blue')],adapter='local_llm',model='tiny',max_tokens=16,repeats=2)
    r=analyze(req)['results'][0]
    assert r['exact_match_accuracy']==1
    assert r['successful_runs']==2 and r['errors']==[]

def test_local_adapter_invalid_url_never_calls_network(monkeypatch):
    monkeypatch.setenv('MODELARENA_LLM_URL','http://example.com/v1/chat/completions')
    r=analyze(BenchmarkRequest(cases=[Case(question='q',context='c',expected_answer='a')],adapter='local_llm',repeats=1))['results'][0]
    assert r['successful_runs']==0 and r['exact_match_accuracy'] is None
    assert r['errors'][0]['error_type']=='ValueError'

def test_local_adapter_real_http_synthetic_transport(monkeypatch):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            import json
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert body['model']=='local-model'
            result=b'{"choices":[{"message":{"content":"Synthetic reply."}}]}'
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(result))); self.end_headers(); self.wfile.write(result)
        def log_message(self,*args): pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        monkeypatch.setenv('MODELARENA_LLM_URL',f'http://127.0.0.1:{server.server_port}/v1/chat/completions')
        r=analyze(BenchmarkRequest(cases=[Case(question='q',context='Synthetic reply.',expected_answer='Synthetic reply.')],adapter='local_llm',repeats=1))['results'][0]
        assert r['exact_match_accuracy']==1 and r['successful_runs']==1
        assert r['mean_latency_ms']>0
    finally:
        server.shutdown();server.server_close();thread.join()
