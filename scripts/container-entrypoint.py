"""Start Uvicorn after granting the unprivileged app user access to /data.

Render mounts persistent disks *after* the Docker image is built; directory ownership
from Dockerfile RUN commands can therefore be obscured by a fresh disk mount.
We start as root only long enough to chown the mount point, then drop privileges.
"""
import os
import pwd
import sys


def main():
    port = os.environ.get('PORT', '8000')
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise SystemExit('Invalid PORT (must be 1..65535)')

    if os.geteuid() == 0:
        user = pwd.getpwnam('appuser')
        os.makedirs('/data', exist_ok=True)
        os.chown('/data', user.pw_uid, user.pw_gid)
        os.setgroups([])
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)

    os.execvp('uvicorn', [
        'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', port,
        '--proxy-headers', '--forwarded-allow-ips', '127.0.0.1',
    ])


if __name__ == '__main__':
    main()
