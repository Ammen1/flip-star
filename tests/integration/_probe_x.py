import pytest
pytestmark = pytest.mark.django_db

def test_probe(client, capsys):
    r = client.post('/api/v1/timwe/sync-order-relation',
                    data=b'<x/>', content_type='text/xml; charset=utf-8')
    with capsys.disabled():
        print(f'\nHTTP {r.status_code}  Content-Type: {r["Content-Type"]}')
        print(f'body ({len(r.content)} bytes):')
        print(r.content.decode())
