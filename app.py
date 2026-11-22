"""Bacon IPA Injector — private, self-hosted .ipa + .dylib injector.

Requires a separately installed zsign executable (https://github.com/zhlynn/zsign).
No Apple signing certificates or passwords are accepted or persisted.
"""
from __future__ import annotations

import asyncio
import os
import plistlib
import re
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

BASE = Path(__file__).resolve().parent
MAX_IPA = int(os.getenv('MAX_IPA_MB', '2048')) * 1024 * 1024
MAX_PLUGIN = int(os.getenv('MAX_PLUGIN_MB', '32')) * 1024 * 1024
MAX_UNPACKED = int(os.getenv('MAX_UNPACKED_MB', '12288')) * 1024 * 1024
MAX_ZIP_ENTRIES = 40000
JOB_TTL = 30 * 60
ZSIGN = os.getenv('ZSIGN_PATH', 'zsign')
APP_PASSWORD = os.getenv('APP_PASSWORD', '')
WORK_DIR = Path(os.getenv('WORK_DIR', tempfile.gettempdir())) / 'bacon-ipa-injector'
WORK_DIR.mkdir(parents=True, exist_ok=True)
JOBS: dict[str, tuple[Path, str, float]] = {}


def _cleanup_expired() -> None:
    now = time.time()
    for key, (folder, _filename, created) in list(JOBS.items()):
        if now - created > JOB_TTL:
            JOBS.pop(key, None)
            shutil.rmtree(folder, ignore_errors=True)


async def _sweeper() -> None:
    while True:
        await asyncio.sleep(60)
        await run_in_threadpool(_cleanup_expired)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_sweeper())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title='Bacon IPA Injector', version='1.1.0', lifespan=lifespan)
# The browser at GitHub Pages is a different origin from the API on Render.
# Never use '*' here for a public file processing server.
CORS_ORIGINS = [x.strip().rstrip('/') for x in os.getenv('CORS_ORIGINS', '').split(',') if x.strip()]
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=['GET', 'POST'],
        allow_headers=['Content-Type', 'X-App-Password'],
    )
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')


def _verify_password(password: str | None) -> None:
    if APP_PASSWORD:
        # constant-time compare prevents simple timing leaks
        import hmac
        if not hmac.compare_digest(password or '', APP_PASSWORD):
            raise HTTPException(401, '網站密碼不正確')


def _save_streamed(upload: UploadFile, target: Path, maximum: int) -> int:
    total = 0
    with target.open('wb') as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise ValueError(f'檔案超出上限 {maximum // 1024 // 1024} MB')
            out.write(chunk)
    if total == 0:
        raise ValueError('檔案不能為空')
    return total


def _arm64_macho_header(header: bytes) -> bool:
    """Accept modern arm64 Mach-O or a fat Mach-O containing an arm64 slice.

    This is a lightweight preflight, not a full binary validator.
    """
    if len(header) < 12:
        return False
    magic = header[:4]
    if magic in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe'):
        # thin Mach-O is little-endian; CPU_TYPE_ARM64 = 0x0100000c
        return int.from_bytes(header[4:8], 'little') == 0x0100000c
    if magic in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf',
                 b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca'):
        big_endian = magic in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf')
        fat_64 = magic in (b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca')
        order = 'big' if big_endian else 'little'
        count = int.from_bytes(header[4:8], order)
        if count > 128:
            return False
        archsize = 32 if fat_64 else 20
        if len(header) < 8 + count * archsize:
            return False
        for i in range(count):
            pos = 8 + i * archsize
            if int.from_bytes(header[pos:pos+4], order) == 0x0100000c:
                return True
    return False


def _check_dylib(path: Path) -> None:
    if path.stat().st_size > MAX_PLUGIN:
        raise ValueError('插件檔案太大')
    # Need up to 128 fat-arch entries * 32 bytes.
    with path.open('rb') as fp:
        if not _arm64_macho_header(fp.read(4096)):
            raise ValueError('插件不是支援 arm64 的 Mach-O .dylib（也可能是其他平台或壓縮檔）')


class AppInfo(NamedTuple):
    display_name: str
    bundle_id: str
    app_dir: str


def _inspect_ipa(ipa: Path) -> AppInfo:
    try:
        with zipfile.ZipFile(ipa) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise ValueError('IPA 含過多檔案')
            size = 0
            names = set()
            roots = {}
            for item in infos:
                path = PurePosixPath(item.filename)
                if (path.is_absolute() or '..' in path.parts or '\\' in item.filename
                    or not item.filename or '\x00' in item.filename):
                    raise ValueError('IPA 含不安全的檔案路徑')
                if item.filename in names:
                    raise ValueError('IPA 有重複路徑，無法安全處理')
                names.add(item.filename)
                if item.flag_bits & 1:
                    raise ValueError('不支援 ZIP 加密的 IPA')
                mode = (item.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise ValueError('不支援內含符號連結的 IPA')
                size += item.file_size
                if size > MAX_UNPACKED:
                    raise ValueError('IPA 解壓後超過設定的容量上限')
                if item.file_size > 50 * 1024 * 1024 and item.compress_size:
                    if item.file_size / item.compress_size > 2000:
                        raise ValueError('IPA 包含異常高壓縮比檔案')
                if len(path.parts) == 3 and path.parts[0] == 'Payload' \
                    and path.parts[1].endswith('.app') and path.parts[2] == 'Info.plist':
                    roots[path.parts[1]] = item.filename
            if len(roots) != 1:
                raise ValueError('IPA 必須包含一個 Payload/*.app/Info.plist')
            app_dir, info_name = next(iter(roots.items()))
            info_item = archive.getinfo(info_name)
            if info_item.file_size > 4 * 1024 * 1024:
                raise ValueError('Info.plist 異常過大')
            plist = plistlib.loads(archive.read(info_name))
            executable = plist.get('CFBundleExecutable')
            if not isinstance(executable, str) or not executable or '/' in executable:
                raise ValueError('IPA 缺少合法的 CFBundleExecutable')
            exe_name = f'Payload/{app_dir}/{executable}'
            if exe_name not in names:
                raise ValueError('IPA 缺少 App 主執行檔')
            with archive.open(exe_name) as f:
                if not _arm64_macho_header(f.read(4096)):
                    raise ValueError('App 主執行檔不是 arm64 Mach-O')
            display = plist.get('CFBundleDisplayName') or plist.get('CFBundleName') or app_dir[:-4]
            bundle = plist.get('CFBundleIdentifier') or '未知'
            return AppInfo(str(display)[:100], str(bundle)[:180], app_dir)
    except (zipfile.BadZipFile, EOFError) as e:
        raise ValueError('不是有效的 IPA / ZIP 檔案') from e
    except plistlib.InvalidFileException as e:
        raise ValueError('Info.plist 格式不正確') from e


def _inject(ipa: Path, tweak: Path, output: Path) -> None:
    # zsign handles the Mach-O load command, library embedding and ad-hoc signing.
    # Never use a shell. The app must later be signed using a legitimate signing tool.
    cmd = [ZSIGN, '-a', '-l', str(tweak), '-o', str(output), str(ipa)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                cwd=str(output.parent), check=False)
    except FileNotFoundError as e:
        raise ValueError('伺服器尚未安裝 zsign，請依 README 設定 ZSIGN_PATH') from e
    except subprocess.TimeoutExpired as e:
        raise ValueError('注入處理逾時（10 分鐘）') from e
    if result.returncode != 0 or not output.is_file() or output.stat().st_size < 100:
        msg = ((result.stderr or '') + '\n' + (result.stdout or '')).strip()
        raise ValueError('zsign 注入失敗：' + (msg[-1500:] if msg else '沒有輸出有效的 IPA'))
    if not zipfile.is_zipfile(output):
        raise ValueError('注入完成，但輸出不是有效的 IPA')
    # Confirm zsign really bundled the dylib instead of silently ignoring the option.
    with zipfile.ZipFile(output) as archive:
        candidates = [x for x in archive.namelist() if x.startswith('Payload/')
                      and x.endswith('/' + tweak.name)]
        if not candidates:
            raise ValueError('輸出的 IPA 沒有包含插件，已停止提供下載')


def _safe_filename(filename: str, fallback: str, extension: str) -> str:
    raw = filename.replace('\\', '/').split('/')[-1]
    base = re.sub(r'[^a-zA-Z0-9._-]', '_', raw)[:100].strip('._')
    if not base.lower().endswith(extension):
        base = fallback
    return base


@app.get('/')
def home():
    return FileResponse(BASE / 'static' / 'index.html', media_type='text/html',
                        headers={'Cache-Control': 'no-store'})


@app.get('/api/config')
def config():
    return JSONResponse({
        'ready': shutil.which(ZSIGN) is not None or Path(ZSIGN).is_file(),
        'password_required': bool(APP_PASSWORD),
        'max_ipa_mb': MAX_IPA // (1024*1024),
        'max_plugin_mb': MAX_PLUGIN // (1024*1024),
        'version': '1.1.0',
    }, headers={'Cache-Control': 'no-store'})


@app.post('/api/inject')
def inject(ipa: UploadFile = File(...), plugin: UploadFile = File(...),
           x_app_password: str | None = Header(default=None)):
    _verify_password(x_app_password)
    if not (ipa.filename or '').lower().endswith('.ipa'):
        raise HTTPException(400, '請上傳 .ipa 檔案')
    if not (plugin.filename or '').lower().endswith('.dylib'):
        raise HTTPException(400, '第一版僅支援 .dylib 插件')

    _cleanup_expired()
    key = uuid.uuid4().hex
    folder = WORK_DIR / key
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    dest_ipa = folder / 'input.ipa'
    plugin_name = _safe_filename(plugin.filename or '', 'plugin.dylib', '.dylib')
    dest_plugin = folder / plugin_name
    out = folder / 'output.ipa'
    try:
        _save_streamed(ipa, dest_ipa, MAX_IPA)
        _save_streamed(plugin, dest_plugin, MAX_PLUGIN)
        info = _inspect_ipa(dest_ipa)
        _check_dylib(dest_plugin)
        _inject(dest_ipa, dest_plugin, out)
        # Remove original inputs as soon as processing is complete.
        dest_ipa.unlink(missing_ok=True)
        dest_plugin.unlink(missing_ok=True)
        original = _safe_filename(ipa.filename or '', 'app.ipa', '.ipa')
        basename = original[:-4] or 'app'
        download_name = f'{basename}-injected.ipa'
        JOBS[key] = (folder, download_name, time.time())
        return JSONResponse({
            'job_id': key,
            'download_url': f'/api/download/{key}',
            'filename': download_name,
            'size_bytes': out.stat().st_size,
            'app_name': info.display_name,
            'bundle_id': info.bundle_id,
            'plugin_name': plugin_name,
            'signing': 'adhoc_only',
        }, headers={'Cache-Control': 'no-store'})
    except ValueError as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(400, str(e)) from e
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        ipa.file.close()
        plugin.file.close()


@app.get('/api/download/{job_id}')
def download(job_id: str):
    if not re.fullmatch(r'[0-9a-f]{32}', job_id):
        raise HTTPException(404, '下載連結不存在')
    _cleanup_expired()
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, '檔案已過期或不存在（保存 30 分鐘）')
    folder, filename, _created = job
    result = folder / 'output.ipa'
    if not result.is_file():
        raise HTTPException(404, '結果檔案不存在')
    return FileResponse(result, filename=filename, media_type='application/octet-stream',
                        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@app.get('/api/health')
def health():
    return {'status': 'ok', 'zsign_available': shutil.which(ZSIGN) is not None or Path(ZSIGN).is_file()}
