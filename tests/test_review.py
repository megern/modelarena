"""Independent baseline and adapter security checks; no real model quality claim."""
from fastapi.testclient import TestClient
from app.main import app
from app.core import Case, BenchmarkRequest, analyze
client=TestClient(app)

def test_context_must_contain_actual_text():
    response=client.post('/analyze',json={'cases':[{'question':'q','context':'  ','expected_answer':'a'}]})
    assert response.status_code==422

def test_baselines_report_all_repeats_and_labels():
    req=BenchmarkRequest(cases=[Case(question='Where is Paris?',context='Paris is in France.',expected_answer='Paris is in France')],repeats=4)
    result=analyze(req)
    assert all(r['attempted_runs']==4 and r['successful_runs']==4 for r in result['results'])
    assert all(r['exact_match_accuracy']==1 for r in result['results'])

def test_local_adapter_rejects_redirect_and_credentials(monkeypatch):
    for url in ['http://user:password@127.0.0.1:8080/v1/chat/completions','file:///tmp/test','http://169.254.169.254/']:
        monkeypatch.setenv('MODELARENA_LLM_URL',url)
        r=analyze(BenchmarkRequest(cases=[Case(question='q',context='c',expected_answer='e')],adapter='local_llm',repeats=1))['results'][0]
        assert r['successful_runs']==0
        assert r['errors'][0]['error_type']=='ValueError'

def test_fixed_docker_bridge_accepts_operator_configuration(monkeypatch):
    import httpx
    from app import core
    original=httpx.Client
    observed=[]
    def handle(request):
        observed.append(str(request.url))
        return httpx.Response(200,json={'choices':[{'message':{'content':'Synthetic answer'}}]})
    def configured_client(**kwargs):
        assert kwargs['trust_env'] is False
        assert kwargs['follow_redirects'] is False
        return original(transport=httpx.MockTransport(handle),**kwargs)
    monkeypatch.setattr(core.httpx,'Client',configured_client)
    monkeypatch.setenv('MODELARENA_LLM_URL','http://host.docker.internal:11434/v1/chat/completions')
    result=analyze(BenchmarkRequest(cases=[Case(question='q',context='Synthetic answer',expected_answer='Synthetic answer')],adapter='local_llm',repeats=1))['results'][0]
    assert result['successful_runs']==1
    assert result['exact_match_accuracy']==1
    assert observed==['http://host.docker.internal:11434/v1/chat/completions']


def test_bridge_lookalikes_userinfo_and_request_url_blocked(monkeypatch):
    from app import core
    def forbid_client(**kwargs):
        raise AssertionError('Disallowed configuration reached HTTP client')
    monkeypatch.setattr(core.httpx,'Client',forbid_client)
    for url in ['http://host.docker.internal.evil.test/v1/chat/completions',
                'http://host.docker.internal@evil.test/v1/chat/completions',
                'http://user@host.docker.internal/v1/chat/completions',
                'http://gateway.docker.internal/v1/chat/completions',
                'http://localhost/v1/chat/completions']:
        monkeypatch.setenv('MODELARENA_LLM_URL',url)
        result=analyze(BenchmarkRequest(cases=[Case(question='q',context='c',expected_answer='a')],adapter='local_llm',repeats=1))['results'][0]
        assert result['successful_runs']==0
        assert result['errors'][0]['error_type']=='ValueError'
    assert client.post('/analyze',json={'cases':[{'question':'q','context':'c','expected_answer':'a'}],'adapter':'local_llm','url':'http://evil.test'}).status_code==422


def test_redirect_response_never_follows_remote_location(monkeypatch):
    import httpx
    from app import core
    original=httpx.Client
    observed=[]
    def handle(request):
        observed.append(request.url.host)
        return httpx.Response(302,headers={'location':'http://example.com/exfiltrate'})
    monkeypatch.setattr(core.httpx,'Client',lambda **kwargs: original(transport=httpx.MockTransport(handle),**kwargs))
    monkeypatch.setenv('MODELARENA_LLM_URL','http://host.docker.internal:11434/v1/chat/completions')
    result=analyze(BenchmarkRequest(cases=[Case(question='q',context='c',expected_answer='a')],adapter='local_llm',repeats=1))['results'][0]
    assert observed==['host.docker.internal']
    assert result['successful_runs']==0
    assert result['errors'][0]['error_type']=='HTTPStatusError'
