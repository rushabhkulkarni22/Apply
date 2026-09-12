"""Use system or project-local Node: python -m backend.frontend build|install|check."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['install','build','check'])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    node = shutil.which('node')
    if not node:
        portable = root/'.tools'/'node-v24.19.0-win-x64'/'node.exe'
        if portable.is_file():
            node = str(portable)
    if not node:
        raise SystemExit('Install Node.js 24 LTS first.')
    node_dir = Path(node).parent
    env = {**os.environ,'PATH':str(node_dir)+os.pathsep+os.environ.get('PATH','')}
    npm_cli = node_dir/'node_modules'/'npm'/'bin'/'npm-cli.js'
    if npm_cli.is_file():
        command = [node,str(npm_cli)]
    else:
        npm = shutil.which('npm',path=env['PATH'])
        if not npm:
            raise SystemExit('npm is missing from the Node installation.')
        command = [npm]
    command += ['ci'] if args.action == 'install' else ['run',args.action]
    raise SystemExit(subprocess.call(command,cwd=root/'apps'/'web',env=env))


if __name__ == '__main__':
    main()
