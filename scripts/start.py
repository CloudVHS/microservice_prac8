import os
import subprocess
import sys

subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], check=True)
name = os.environ.get('SERVICE_NAME', 'user')
if name not in {'user', 'practice', 'grammar', 'lexicon', 'dictionary', 'reference', 'payment', 'notification'}:
    raise SystemExit('Unknown SERVICE_NAME')
os.execvp(sys.executable, [sys.executable, '-m', 'uvicorn', f'app.{name}.main:app', '--host', '0.0.0.0', '--port', '8000'])
