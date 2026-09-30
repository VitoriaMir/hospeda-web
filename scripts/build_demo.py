"""Gera uma demonstração estática e navegável do sistema para o GitHub Pages.

Renderiza as telas reais da aplicação (com a massa de dados fictícia) usando o
cliente de testes do Flask, reescreve os links para arquivos .html e injeta um
script de "modo demonstração" que impede alterações e explica o que acontece
na versão instalada.

Uso:
    python scripts/build_demo.py            # gera em _site/
    python scripts/build_demo.py saida/     # gera em outra pasta
"""
import html
import json
import os
import re
import secrets
import shutil
import stat
import sys
import tempfile
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / '_site'
DEMO_ASSETS = ROOT / 'demo'

# Base temporária e limpa: a demo nunca usa conpec.db nem a marca local.
tmp_dir = tempfile.mkdtemp(prefix='conpec-demo-')
os.environ['CONPEC_DATABASE_URL'] = f"sqlite:///{Path(tmp_dir, 'demo.db').as_posix()}"
os.environ.setdefault('CONPEC_SECRET_KEY', secrets.token_hex(32))
sys.path.insert(0, str(ROOT))

import app.core.branding as branding  # noqa: E402
branding.LOCAL_FILE = Path(tmp_dir, 'sem-marca-local.json')

import run_web  # noqa: E402

app = run_web.app
SEEDS = [
    '/dashboard', '/rooms', '/guests', '/stays', '/bookings', '/calendar',
    '/finance', '/finance?kind=PAGAMENTOS', '/finance?kind=DESPESAS',
    '/operations', '/employees', '/change-password',
]
MAX_PAGES = 400
ATTR_URL = re.compile(r'''(?P<attr>(?<![.\w])(?:href|src|action))=(?P<q>["'])(?P<url>/[^"']*)(?P=q)''')
JS_URL = re.compile(r'''(?P<q>["'])(?P<url>/[A-Za-z][^"'\s<>]*)(?P=q)''')


def page_file(url):
    """'/guest/3' -> 'guest-3.html'; '/finance?kind=X' -> 'finance--kind-x.html'."""
    parts = urlsplit(url)
    name = parts.path.strip('/').replace('/', '-') or 'dashboard'
    if parts.query:
        name += '--' + re.sub(r'[^a-z0-9]+', '-', unquote(parts.query).lower()).strip('-')
    return name + '.html'


def force_remove(func, path, _exc):
    """No Windows, arquivos copiados podem vir somente leitura e travar o rmtree."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def is_route(path):
    adapter = app.url_map.bind('localhost')
    for method in ('GET', 'POST'):
        try:
            adapter.match(path, method=method)
            return True
        except Exception:
            continue
    return False


def crawl():
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_id'] = 1
        s['username'] = 'admin'
        s['role'] = 'ADMINISTRADOR'
        s['must_change_password'] = False

    pages = {}
    queue = deque(SEEDS)
    while queue and len(pages) < MAX_PAGES:
        url = queue.popleft()
        if url in pages:
            continue
        resp = client.get(url)
        if resp.status_code != 200 or not resp.mimetype == 'text/html':
            print(f'  ignorado {url} ({resp.status_code})')
            continue
        body = resp.get_data(as_text=True)
        pages[url] = body
        for match in ATTR_URL.finditer(body):
            if match['attr'] != 'href':
                continue
            link = html.unescape(match['url']).split('#')[0]
            if link and not link.startswith(('/static/', '/logout')) and link != '/' and link not in pages:
                queue.append(link)

    pages['/login'] = app.test_client().get('/login').get_data(as_text=True)
    return pages


def build():
    pages = crawl()
    routes = {url: page_file(url) for url in pages}
    known_paths = {urlsplit(url).path: page_file(urlsplit(url).path) for url in pages if urlsplit(url).path in pages}

    def rewrite(raw, in_attr):
        url = html.unescape(raw)
        path_query, _, fragment = url.partition('#')
        fragment = '#' + fragment if fragment else ''
        path = urlsplit(path_query).path
        query = urlsplit(path_query).query
        if path.startswith('/static/'):
            return path_query[1:] + fragment
        if path == '/logout':
            return 'login.html'
        if path == '/':
            return 'dashboard.html' if in_attr else None
        # Em JS a URL pode ser concatenada (ex.: '/finance?kind=' + aba), então
        # só atributos apontam direto para a variante; o demo.js redireciona as demais.
        if in_attr and path_query in routes:
            return routes[path_query] + fragment
        if path in known_paths:
            return known_paths[path] + ('?' + query if query else '') + fragment
        if in_attr or is_route(path):
            return '#demo'
        return None

    def attr_sub(m):
        new = rewrite(m['url'], True)
        return f"{m['attr']}={m['q']}{html.escape(new, quote=True)}{m['q']}"

    def js_sub(m):
        new = rewrite(m['url'], False)
        return m.group(0) if new is None else f"{m['q']}{new}{m['q']}"

    if OUT.exists():
        shutil.rmtree(OUT, onexc=force_remove)
    OUT.mkdir(parents=True)

    for url, body in pages.items():
        body = ATTR_URL.sub(attr_sub, body)
        body = JS_URL.sub(js_sub, body)
        head_inject = (
            f'<meta name="demo-path" content="{html.escape(url, quote=True)}">'
            '<link rel="stylesheet" href="demo/demo.css">'
            '<script src="demo/routes.js"></script><script src="demo/demo.js"></script>'
        )
        body = body.replace('</head>', head_inject + '</head>', 1)
        (OUT / routes[url]).write_text(body, encoding='utf-8')

    shutil.copytree(ROOT / 'static', OUT / 'static', ignore=shutil.ignore_patterns('brand'))
    shutil.copytree(DEMO_ASSETS, OUT / 'demo', ignore=shutil.ignore_patterns('index.html'))
    shutil.copy(DEMO_ASSETS / 'index.html', OUT / 'index.html')
    (OUT / 'demo' / 'routes.js').write_text(
        'window.DEMO_ROUTES=' + json.dumps(routes, ensure_ascii=False) + ';', encoding='utf-8')
    (OUT / '.nojekyll').write_text('', encoding='utf-8')
    print(f'{len(pages)} páginas geradas em {OUT}')


if __name__ == '__main__':
    try:
        build()
    finally:
        run_web.SessionLocal.kw['bind'].dispose()
        shutil.rmtree(tmp_dir, ignore_errors=True)
