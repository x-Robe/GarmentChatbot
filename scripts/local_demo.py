"""Mac demo supervisor: private env, loopback API, Quick/named tunnel, preview.

No cloud deployment or Git push is performed by this program.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
CONTROL = RUNTIME / 'control.sock'
LAST_HEALTH_ERROR = 'not checked'
SECRET_NAMES = ('POE_API', 'OPENAI_API_KEY', 'QDRANT_API', 'HF_TOKEN')


def settings():
    from dotenv import dotenv_values
    file = ROOT / '.env.local'
    if file.exists() and file.stat().st_mode & 0o077:
        raise ValueError('Run chmod 600 .env.local before starting.')
    values = dotenv_values(file, interpolate=False) if file.exists() else {}
    env = {**{k: v for k, v in values.items() if v is not None}, **os.environ}
    env['PYTHON_DOTENV_DISABLED'] = '1'  # Never read historical backend/.env.
    env['PYTHONUNBUFFERED'] = '1'
    env.setdefault('LOCAL_API_PORT', '8765')
    env.setdefault('LOCAL_FRONTEND_PORT', '8766')
    for name in ('LOCAL_API_PORT', 'LOCAL_FRONTEND_PORT'):
        if not 1024 <= int(env[name]) <= 65535:
            raise ValueError(name + ' must be between 1024 and 65535')
    if env['LOCAL_API_PORT'] == env['LOCAL_FRONTEND_PORT']:
        raise ValueError('API and preview ports must be different')
    env.setdefault('CORS_ORIGINS', 'https://garmentchatbot.web.app,https://garmentchatbot.firebaseapp.com,'
                   f'http://127.0.0.1:{env["LOCAL_FRONTEND_PORT"]},http://localhost:{env["LOCAL_FRONTEND_PORT"]}')
    env.setdefault('API_MAX_INFLIGHT', '2')
    env.setdefault('API_REQUESTS_PER_MINUTE', '30')
    return env


def missing_settings(env):
    names = ['OPENAI_MODEL', 'QDRANT_URL', 'QDRANT_COLLECTION', 'CLIP_MODEL', 'CORS_ORIGINS']
    if env.get('POE_API', '').strip():
        names += ['POE_URL']
    elif not env.get('OPENAI_API_KEY', '').strip():
        names += ['POE_API or OPENAI_API_KEY']
    if env.get('QDRANT_URL', '').strip():
        names += ['QDRANT_API']  # This deployment uses authenticated Qdrant Cloud.
    return [name for name in names if not env.get(name, '').strip()]


def reject_historical_secrets(env):
    candidates = {name: env.get(name, '').strip() for name in SECRET_NAMES}
    if not any(candidates.values()):
        return
    commits = subprocess.check_output(['git', 'rev-list', '--all'], cwd=ROOT, text=True).splitlines()
    for commit in commits:
        for path in ('.env', 'backend/.env', 'Credentials/qdrant'):
            result = subprocess.run(['git', 'show', f'{commit}:{path}'], cwd=ROOT, capture_output=True)
            if result.returncode:
                continue
            for name, value in candidates.items():
                if value and len(value) >= 10 and value.encode() in result.stdout:
                    raise ValueError(name + ' matches exposed Git history; supply a rotated credential.')


def validate_live(env, allow_historical=False):
    missing = missing_settings(env)
    if missing:
        raise ValueError('Missing private settings: ' + ', '.join(missing))
    for name in ('QDRANT_URL', 'POE_URL'):
        if env.get(name) and urlparse(env[name]).scheme != 'https':
            raise ValueError(name + ' must use HTTPS')
    if not env.get('POE_API'):
        env.pop('POE_API', None)
        env.pop('POE_URL', None)
    if not allow_historical:
        reject_historical_secrets(env)


def ask(command):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(str(CONTROL))
            client.sendall((command + '\n').encode())
            return json.loads(client.recv(65536))
    except PermissionError:
        raise ValueError('Local control socket access denied. Run this command in your normal Mac terminal.') from None
    except (OSError, ValueError):
        return None


def healthy(url):
    global LAST_HEALTH_ERROR
    try:
        with urlopen(url + '/api/health', timeout=2) as response:
            valid = response.status == 200 and json.load(response) == {'status': 'ok'}
            LAST_HEALTH_ERROR = 'unexpected health response' if not valid else ''
            return valid
    except Exception as exc:
        LAST_HEALTH_ERROR = type(exc).__name__ + '/' + type(getattr(exc, 'reason', None)).__name__
        return False


def check_port(port):
    with socket.socket() as test:
        test.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            test.bind(('127.0.0.1', int(port)))
        except OSError:
            raise ValueError('Port ' + str(port) + ' is already occupied; no existing process was stopped.') from None


def configure_frontend(origin):
    parsed = urlparse(origin)
    if (parsed.scheme != 'https' or not parsed.hostname
            or not re.fullmatch(r'[a-zA-Z0-9.-]+', parsed.hostname) or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('Frontend API must be an HTTPS origin without credentials/path/query')
    source = ROOT / 'frontend' / 'config.js'
    original = source.read_text()
    backup = RUNTIME / 'frontend-config.original.js'
    if not backup.exists():
        backup.write_text(original)
    updated, count = re.subn(r"export const API_BASE_URL = '[^']*';",
                              "export const API_BASE_URL = '" + origin.rstrip('/') + "';", original)
    if count != 1:
        raise ValueError('Unexpected config.js shape; no frontend changes made')
    source.write_text(updated)
    public = RUNTIME / 'firebase' / 'public'
    public.mkdir(parents=True, exist_ok=True)
    # Stage only browser assets; never serve repository/.env or backend paths.
    for file in (ROOT / 'frontend').rglob('*'):
        if not file.is_file() or file.is_symlink():
            continue
        relative = file.relative_to(ROOT / 'frontend')
        if (any(part.startswith('.') or part == 'node_modules' for part in relative.parts)
                or file.name.endswith('.test.js') or file.name == 'package.json'
                or file.suffix.lower() not in ('.js', '.html', '.css', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.ico')):
            continue
        target = public / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
    config = json.loads((ROOT / 'firebase.json').read_text())
    config['hosting']['public'] = 'public'
    (public.parent / 'firebase.json').write_text(json.dumps(config, indent=2) + '\n')
    shutil.copy2(ROOT / '.firebaserc', public.parent / '.firebaserc')
    return public


def supervise(transport_only, allow_historical=False):
    os.umask(0o077)
    env = settings()
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    lock = (RUNTIME / 'session.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise ValueError('A demo supervisor already owns this runtime directory') from None
    binary = ROOT / '.tools' / 'cloudflared'
    if not binary.is_file():
        raise ValueError('Run scripts/install_cloudflared.sh first')
    if transport_only:
        for name in (*SECRET_NAMES, 'QDRANT_URL', 'POE_URL'):
            env[name] = ''
    else:
        validate_live(env, allow_historical)
    for name in ('LOCAL_API_PORT', 'LOCAL_FRONTEND_PORT'):
        check_port(env[name])
    api_url = 'http://127.0.0.1:' + env['LOCAL_API_PORT']
    state = {'status': 'starting', 'transport_only': transport_only,
             'api': api_url, 'preview': 'http://127.0.0.1:' + env['LOCAL_FRONTEND_PORT'],
             'tunnel': None, 'supervisor_pid': os.getpid(), 'historical_credentials_owner_exception': allow_historical}
    stop = threading.Event()
    children, handles = [], []
    CONTROL.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(CONTROL))
    server.listen(5)
    server.settimeout(1)

    def control():
        while not stop.is_set():
            try:
                connection, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with connection:
                connection.settimeout(2)
                try:
                    command = connection.recv(100).decode().strip()
                    connection.sendall(json.dumps(state).encode())
                    if command == 'stop':
                        stop.set()
                except OSError:
                    pass
    threading.Thread(target=control, daemon=True).start()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    def launch(command, logname):
        handle = (RUNTIME / logname).open('w')
        handles.append(handle)
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=handle,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        children.append(process)
        return process

    try:
        api = launch([sys.executable, '-m', 'uvicorn', 'api:app', '--app-dir', str(ROOT / 'backend'),
                      '--host', '127.0.0.1', '--port', env['LOCAL_API_PORT'], '--workers', '1',
                      '--timeout-keep-alive', '5', '--no-access-log'], 'backend.log')
        state['backend_pid'] = api.pid
        deadline = time.monotonic() + 30
        while not healthy(api_url):
            if stop.wait(0.25) or api.poll() is not None or time.monotonic() > deadline:
                raise ValueError('Local API did not start; inspect private .runtime/backend.log')
        config_path = env.get('CLOUDFLARED_CONFIG', '').strip()
        if config_path:
            config_path = str(Path(config_path).expanduser().resolve())
            if not Path(config_path).is_file():
                raise ValueError('CLOUDFLARED_CONFIG file not found')
            origin = env.get('LOCAL_TUNNEL_ORIGIN', '').strip()
            if not origin:
                raise ValueError('LOCAL_TUNNEL_ORIGIN required for an existing named tunnel')
            tunnel_command = [str(binary), '--no-autoupdate', 'tunnel', '--config', config_path,
                              '--protocol', 'http2', 'run']
        else:
            quick_config = RUNTIME / 'quick-config.yml'
            quick_config.write_text('{}\n')
            origin = None
            tunnel_command = [str(binary), '--no-autoupdate', 'tunnel', '--config', str(quick_config),
                              '--url', api_url, '--protocol', 'http2']
        tunnel = launch(tunnel_command, 'tunnel.log')
        state['tunnel_pid'] = tunnel.pid
        deadline = time.monotonic() + 75
        while not origin:
            text = (RUNTIME / 'tunnel.log').read_text(errors='replace')
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', text)
            if match:
                origin = match.group(0)
                break
            if stop.wait(0.25) or tunnel.poll() is not None or time.monotonic() > deadline:
                raise ValueError('Quick Tunnel failed; inspect private .runtime/tunnel.log')
        deadline = time.monotonic() + 120
        while not healthy(origin):
            if stop.wait(0.5) or tunnel.poll() is not None or time.monotonic() > deadline:
                raise ValueError('Tunnel HTTPS liveness failed (' + LAST_HEALTH_ERROR + '); inspect private tunnel.log')
        public = configure_frontend(origin)
        launch([sys.executable, '-m', 'http.server', env['LOCAL_FRONTEND_PORT'], '--bind', '127.0.0.1',
                '--directory', str(public)], 'frontend-preview.log')
        if shutil.which('caffeinate'):
            launch(['caffeinate', '-i', '-w', str(os.getpid())], 'keep-awake.log')
        state.update(status='running', tunnel=origin)
        (RUNTIME / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
        while not stop.wait(1):
            if any(child.poll() is not None for child in children):
                raise ValueError('A managed process exited; stopping the demo. Inspect private .runtime logs.')
    except Exception as exc:
        state.update(status='failed', error=str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
        print(state['error'], flush=True)
    finally:
        stop.set()
        for child in reversed(children):
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for child in reversed(children):
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
        for handle in handles:
            handle.close()
        server.close()
        CONTROL.unlink(missing_ok=True)
        if state['status'] != 'failed':
            state['status'] = 'stopped'
        (RUNTIME / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['start', 'stop', 'status', 'check', 'verify', 'configure-frontend', 'restore-frontend', '_serve'])
    parser.add_argument('--transport-only', action='store_true', help='Expose health/images only; clear integration credentials')
    parser.add_argument('--allow-historical-credentials', action='store_true',
                        help='Explicit owner exception; default history checks remain enabled')
    parser.add_argument('--models', action='store_true')
    parser.add_argument('--llm', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == '_serve':
        supervise(args.transport_only, args.allow_historical_credentials)
        return
    if args.command == 'status':
        print(json.dumps(ask('status') or {'status': 'not running'}, indent=2))
        return
    if args.command == 'stop':
        state = ask('stop')
        if not state:
            print('No demo supervisor running; no process was stopped.')
            return
        for _ in range(150):
            if not CONTROL.exists():
                print('Stopped owned backend, tunnel, preview and keep-awake processes.')
                return
            time.sleep(0.2)
        raise ValueError('Shutdown still in progress; retry status, do not kill unrelated processes.')
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    if args.command == 'restore-frontend':
        backup = RUNTIME / 'frontend-config.original.js'
        if not backup.is_file():
            raise ValueError('No saved pre-demo frontend config')
        (ROOT / 'frontend/config.js').write_text(backup.read_text())
        print('Restored pre-demo local frontend config; no Firebase deployment performed.')
        return
    if args.command == 'configure-frontend':
        state = ask('status')
        if not state or not state.get('tunnel'):
            raise ValueError('Start the tunnel first')
        configure_frontend(state['tunnel'])
        print('Updated local frontend config and private Firebase staging directory; not deployed.')
        return
    env = settings()
    if args.command in ('check', 'verify'):
        validate_live(env, args.allow_historical_credentials)
        print('Required private settings are present; explicit owner exception enabled.' if args.allow_historical_credentials else 'Required private settings are present and do not match fetched Git history; live validity not yet verified.')
        if args.command == 'verify':
            command = [sys.executable, str(ROOT / 'scripts/verify_integrations.py')]
            if args.models: command.append('--models')
            if args.llm: command.append('--llm')
            raise SystemExit(subprocess.call(command, cwd=ROOT, env=env))
        return
    if ask('status'):
        raise ValueError('Demo is already running. Use status/stop first.')
    if not args.transport_only:
        validate_live(env, args.allow_historical_credentials)
    log = (RUNTIME / 'supervisor.log').open('w')
    command = [sys.executable, str(Path(__file__).resolve()), '_serve']
    if args.transport_only: command.append('--transport-only')
    if args.allow_historical_credentials: command.append('--allow-historical-credentials')
    supervisor = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                  env=env, start_new_session=True)
    log.close()
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        state = ask('status')
        if state and state['status'] == 'running':
            print(json.dumps(state, indent=2))
            print('Frontend config staged locally. Firebase is unchanged.')
            return
        if supervisor.poll() is not None:
            raise ValueError('Startup failed; inspect private .runtime/supervisor.log and tunnel.log.')
        time.sleep(0.5)
    ask('stop')
    raise ValueError('Startup timed out; stopping owned demo processes.')


if __name__ == '__main__':
    try:
        main()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print('Demo operation failed (' + type(exc).__name__ + '). Inspect private logs.', file=sys.stderr)
        sys.exit(1)
