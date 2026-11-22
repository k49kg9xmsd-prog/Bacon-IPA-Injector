import io
import plistlib
import struct
import zipfile

import pytest
from fastapi.testclient import TestClient

import app as api


ARM64_MAGIC = b'\xcf\xfa\xed\xfe' + struct.pack('<I', 0x0100000c) + b'\x00' * 64


def make_ipa():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('Payload/Demo.app/Info.plist', plistlib.dumps({
            'CFBundleIdentifier': 'com.example.demo',
            'CFBundleExecutable': 'Demo',
            'CFBundleDisplayName': '示範 App',
        }))
        z.writestr('Payload/Demo.app/Demo', ARM64_MAGIC)
    return stream.getvalue()


def make_dylib():
    return ARM64_MAGIC


def fake_inject(ipa, tweak, output):
    # Fake external tool; verifies API behavior, not real Mach-O rewriting.
    output.write_bytes(ipa.read_bytes())
    with zipfile.ZipFile(output, 'a') as z:
        z.writestr('Payload/Demo.app/' + tweak.name, tweak.read_bytes())


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(api, 'WORK_DIR', tmp_path)
    monkeypatch.setattr(api, 'APP_PASSWORD', '')
    monkeypatch.setattr(api, '_inject', fake_inject)
    api.JOBS.clear()
    with TestClient(api.app) as c:
        yield c
    api.JOBS.clear()


def test_api_success_and_download(client):
    response = client.post('/api/inject', files={
        'ipa': ('demo.ipa', make_ipa(), 'application/octet-stream'),
        'plugin': ('BaconClicker.dylib', make_dylib(), 'application/octet-stream'),
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['app_name'] == '示範 App'
    assert result['bundle_id'] == 'com.example.demo'
    assert result['signing'] == 'adhoc_only'
    assert result['filename'] == 'demo-injected.ipa'
    downloaded = client.get(result['download_url'])
    assert downloaded.status_code == 200
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as z:
        assert 'Payload/Demo.app/BaconClicker.dylib' in z.namelist()


def test_non_macho_plugin_rejected(client):
    response = client.post('/api/inject', files={
        'ipa': ('demo.ipa', make_ipa()),
        'plugin': ('bad.dylib', b'random text'),
    })
    assert response.status_code == 400
    assert 'arm64' in response.json()['detail']


def test_fake_ipa_rejected(client):
    response = client.post('/api/inject', files={
        'ipa': ('demo.ipa', b'not a zip file'),
        'plugin': ('good.dylib', make_dylib()),
    })
    assert response.status_code == 400
    assert 'IPA' in response.json()['detail']


def test_password_required(client, monkeypatch):
    monkeypatch.setattr(api, 'APP_PASSWORD', 'mypassword')
    files = {'ipa': ('demo.ipa', make_ipa()), 'plugin': ('good.dylib', make_dylib())}
    assert client.post('/api/inject', files=files).status_code == 401
    response = client.post('/api/inject', headers={'X-App-Password': 'mypassword'}, files=files)
    assert response.status_code == 200


def test_zip_traversal_rejected(client):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('../evil', b'bad')
        z.writestr('Payload/Demo.app/Info.plist', plistlib.dumps({'CFBundleExecutable':'Demo'}))
        z.writestr('Payload/Demo.app/Demo', ARM64_MAGIC)
    response = client.post('/api/inject', files={
        'ipa': ('danger.ipa', stream.getvalue()),
        'plugin': ('good.dylib', make_dylib()),
    })
    assert response.status_code == 400
    assert '不安全' in response.json()['detail']


def test_invalid_download(client):
    assert client.get('/api/download/../../../etc/passwd').status_code == 404
    assert client.get('/api/download/' + '0'*32).status_code == 404


def test_invalid_extension(client):
    response = client.post('/api/inject', files={
        'ipa': ('demo.zip', make_ipa()),
        'plugin': ('good.dylib', make_dylib()),
    })
    assert response.status_code == 400
    assert '.ipa' in response.json()['detail']


def test_github_page_frontend_uses_configured_endpoint():
    from pathlib import Path
    frontend = Path(__file__).resolve().parents[1] / 'docs'
    html = (frontend / 'index.html').read_text()
    js = (frontend / 'app.js').read_text()
    assert './config.js' in html
    assert "apiUrl('/api/inject')" in js
    assert 'apiUrl(payload.download_url)' in js
