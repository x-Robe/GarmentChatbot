"""Prepare a credential-free, allowlisted Cloud Build context from working assets.

Does not call Google Cloud, build/push an image, alter Firebase or stop the Mac.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def link_or_copy(source, destination):
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)
    return str(destination)


def prepare():
    runtime = ROOT / '.runtime/cloudrun'
    runtime.mkdir(parents=True, exist_ok=True)
    context = Path(tempfile.mkdtemp(prefix='build-', dir=runtime))
    for name in ('Dockerfile', '.dockerignore', '.gcloudignore', 'backend/api.py',
                 'backend/chatbot.py', 'backend/SKILL.md', 'backend/requirements.txt'):
        target = context / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    for directory in ('backend/src', 'backend/data/samples', 'deployment/cloudrun'):
        source = ROOT / directory
        for file in source.rglob('*'):
            if not file.is_file() or file.suffix not in ('.py', '.json', '.txt', '.yaml'):
                continue
            if '__pycache__' in file.parts:
                continue
            target = context / file.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
    images = context / 'data/images'
    images.mkdir(parents=True)
    source_images = list((ROOT / 'data/images').rglob('*.jpg'))
    for source in source_images:
        target = images / source.relative_to(ROOT / 'data/images')
        target.parent.mkdir(parents=True, exist_ok=True)
        link_or_copy(source, target)
    manifest = json.loads((ROOT / 'deployment/cloudrun/models.json').read_text())
    hub = Path.home() / '.cache/huggingface/hub'
    model_bytes = 0
    for model, info in manifest.items():
        name = 'models--' + model.replace('/', '--')
        source = hub / name
        snapshot = source / 'snapshots' / info['revision']
        if not snapshot.is_dir():
            raise RuntimeError('Missing pinned model cache: ' + model)
        target = context / '.cloudrun-models' / name
        destination_snapshot = target / 'snapshots' / info['revision']
        destination_snapshot.mkdir(parents=True)
        # Materialize each pinned file exactly once. Recent HF caches may use
        # centralized blobs; no absolute or escaping symlinks enter the image.
        for file in snapshot.rglob('*'):
            if not file.is_file():
                continue
            resolved = file.resolve()
            resolved.relative_to(hub.resolve())
            destination = destination_snapshot / file.relative_to(snapshot)
            destination.parent.mkdir(parents=True, exist_ok=True)
            link_or_copy(resolved, destination)
            model_bytes += resolved.stat().st_size
        (target / 'refs').mkdir()
        (target / 'refs/main').write_text(info['revision'])
    # Protect against accidental credentials in future context changes.
    for file in context.rglob('*'):
        if file.name.startswith('.env') or file.name in ('cert.pem', 'firebase-tools.json'):
            raise RuntimeError('Forbidden private file in container context')
    inventory = {'context': str(context), 'catalog_count': len(source_images),
                 'catalog_bytes': sum(p.stat().st_size for p in source_images),
                 'model_blob_bytes': model_bytes, 'models': manifest,
                 'cloud_resources_created': False}
    (runtime / 'context.json').write_text(json.dumps(inventory, indent=2) + '\n')
    # Snapshot the deployed Mac frontend for rollback; never overwrite the running staging directory.
    rollback = runtime / 'rollback/firebase'
    if not rollback.exists():
        shutil.copytree(ROOT / '.runtime/firebase', rollback)
    print(json.dumps(inventory, indent=2))


if __name__ == '__main__':
    prepare()
