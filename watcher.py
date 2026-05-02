"""
AutoPush — monitora alterações na pasta ETL e envia automaticamente ao GitHub.
Usa debounce de 20s para agrupar mudanças rápidas (ex: pipeline.py rodando).
"""
import time
import subprocess
import os
import threading
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(REPO_DIR, 'auto_push.log')
DEBOUNCE_SECONDS = 20
IGNORE = {'.git', '__pycache__', 'auto_push.log', '.pyc', '.pyo'}


def log(msg):
    ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def git_push():
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=REPO_DIR, capture_output=True, text=True, encoding='utf-8'
        )
        if not result.stdout.strip():
            return

        arquivos = [l.strip() for l in result.stdout.strip().splitlines()]
        log(f'Alterações detectadas: {", ".join(arquivos[:5])}{"..." if len(arquivos) > 5 else ""}')

        subprocess.run(['git', 'add', '-u'], cwd=REPO_DIR)

        msg = f'Auto-update: {datetime.now().strftime("%d/%m/%Y %H:%M")}'
        r_commit = subprocess.run(
            ['git', 'commit', '-m', msg],
            cwd=REPO_DIR, capture_output=True, text=True, encoding='utf-8'
        )
        if r_commit.returncode != 0:
            return

        log(f'Commit: {msg}')

        r_push = subprocess.run(
            ['git', 'push', 'origin', 'main'],
            cwd=REPO_DIR, capture_output=True, text=True, encoding='utf-8'
        )
        if r_push.returncode == 0:
            log('GitHub Pages atualizado com sucesso.')
        else:
            log(f'Erro no push: {r_push.stderr.strip()}')
    except Exception as e:
        log(f'Erro inesperado: {e}')


class ChangeHandler(FileSystemEventHandler):
    def __init__(self):
        self._timer = None
        self._lock = threading.Lock()

    def _ignorar(self, path):
        return any(p in path for p in IGNORE)

    def on_modified(self, event):
        if event.is_directory or self._ignorar(event.src_path):
            return
        log(f'Modificado: {os.path.basename(event.src_path)}')
        self._agendar_push()

    def on_created(self, event):
        if event.is_directory or self._ignorar(event.src_path):
            return
        log(f'Criado: {os.path.basename(event.src_path)}')
        self._agendar_push()

    def _agendar_push(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, git_push)
            self._timer.start()


if __name__ == '__main__':
    log('=== AutoPush iniciado ===')
    log(f'Pasta monitorada: {REPO_DIR}')
    log(f'Aguarda {DEBOUNCE_SECONDS}s de inatividade antes de cada commit.')

    handler = ChangeHandler()
    observer = Observer()
    observer.schedule(handler, REPO_DIR, recursive=False)
    observer.start()

    try:
        while observer.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    observer.stop()
    observer.join()
    log('=== AutoPush encerrado ===')
