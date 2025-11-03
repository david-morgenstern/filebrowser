import shutil
import tempfile
import zipfile
import mimetypes
import logging
import asyncio
import sqlite3
import subprocess
import json
import os
from datetime import datetime
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import StreamingResponse, Response

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
DB_PATH = '/app/db/filebrowser_history.db'
DB_DIR = '/app/db'
DATA_DIR = '/app/data'

# File type categories
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg')
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.wmv', '.m4v')
TEXT_EXTENSIONS = ('.txt', '.md', '.log', '.json', '.xml', '.csv', '.py', '.js', '.html', '.css', '.sh', '.yml', '.yaml', '.ini', '.conf')
AUDIO_EXTENSIONS = ('.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac')

MIME_TYPE_MAP = {
    '.mp4': 'video/mp4', '.m4v': 'video/mp4', '.webm': 'video/webm',
    '.mkv': 'video/x-matroska', '.avi': 'video/x-msvideo',
    '.mov': 'video/quicktime', '.flv': 'video/x-flv', '.wmv': 'video/x-ms-wmv',
    '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.aac': 'audio/aac',
    '.wav': 'audio/wav', '.flac': 'audio/flac', '.ogg': 'audio/ogg',
    '.oga': 'audio/ogg', '.opus': 'audio/opus',
}

# ============================================
# Database Functions
# ============================================

@contextmanager
def get_db():
    """Context manager for database connections"""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()

def init_db():
    """Initialize the database schema"""
    try:
        with get_db() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS watch_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER,
                    first_watched TIMESTAMP NOT NULL,
                    last_watched TIMESTAMP NOT NULL,
                    view_count INTEGER DEFAULT 1
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_ip_watched ON watch_history(ip_address, last_watched DESC)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_file_watched ON watch_history(file_path, last_watched DESC)')
            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

def track_view(ip_address: str, file_path: str, file_name: str, file_type: str, file_size: int):
    """Track a file view in the database"""
    try:
        with get_db() as conn:
            existing = conn.execute(
                'SELECT id, view_count FROM watch_history WHERE ip_address = ? AND file_path = ?',
                (ip_address, file_path)
            ).fetchone()

            if existing:
                conn.execute(
                    'UPDATE watch_history SET last_watched = ?, view_count = ? WHERE id = ?',
                    (datetime.now(), existing['view_count'] + 1, existing['id'])
                )
            else:
                conn.execute(
                    '''INSERT INTO watch_history (ip_address, file_path, file_name, file_type, file_size, first_watched, last_watched)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (ip_address, file_path, file_name, file_type, file_size, datetime.now(), datetime.now())
                )
    except Exception as e:
        logger.error(f"Failed to track view: {e}")

# ============================================
# File Type Functions
# ============================================

def get_file_type(filename):
    """Determine file type from extension"""
    ext = os.path.splitext(filename.lower())[1]
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    elif ext in VIDEO_EXTENSIONS:
        return 'video'
    elif ext in AUDIO_EXTENSIONS:
        return 'audio'
    elif ext in TEXT_EXTENSIONS:
        return 'text'
    elif ext == '.pdf':
        return 'pdf'
    elif ext in ('.zip', '.tar', '.gz', '.rar', '.7z'):
        return 'archive'
    return 'file'

def get_mime_type(file_path):
    """Get MIME type with explicit mappings"""
    ext = os.path.splitext(file_path.lower())[1]
    if ext in MIME_TYPE_MAP:
        return MIME_TYPE_MAP[ext]
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or 'application/octet-stream'

# ============================================
# Video Functions
# ============================================

def get_video_info(file_path):
    """Get video metadata including duration and codec"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', '-select_streams', 'v:0',
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            logger.error(f"ffprobe failed for {file_path}")
            return None

        data = json.loads(result.stdout)
        info = {'duration': 0, 'codec': 'unknown', 'needs_transcode': False}

        if 'format' in data and 'duration' in data['format']:
            info['duration'] = float(data['format']['duration'])

        if data.get('streams'):
            codec = data['streams'][0].get('codec_name', '').lower()
            info['codec'] = codec
            unsupported = ['xvid', 'divx', 'mpeg4', 'msmpeg4', 'wmv', 'flv1', 'vp6']
            info['needs_transcode'] = codec in unsupported

        return info
    except Exception as e:
        logger.error(f"Error getting video info: {e}")
        return None

# ============================================
# FastAPI App Setup
# ============================================

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    init_db()

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory="/app/templates")

# ============================================
# API Endpoints
# ============================================

@app.get('/api/video-info/{file_path:path}')
async def get_video_metadata(file_path: str):
    """Get video metadata (duration, codec, etc.)"""
    full_path = os.path.join(DATA_DIR, file_path)

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail='File not found')

    info = get_video_info(full_path)
    if not info:
        raise HTTPException(status_code=500, detail='Could not read video metadata')

    return JSONResponse(info)

@app.get('/api/history')
async def get_history(request: Request, limit: int = 50):
    """Get watch history for the current user's IP"""
    client_ip = request.client.host if request.client else "unknown"

    try:
        with get_db() as conn:
            rows = conn.execute(
                '''SELECT file_path, file_name, file_type, file_size, first_watched, last_watched, view_count
                   FROM watch_history WHERE ip_address = ? ORDER BY last_watched DESC LIMIT ?''',
                (client_ip, limit)
            ).fetchall()

            history = [dict(row) for row in rows]
            return JSONResponse({'history': history, 'count': len(history)})
    except Exception as e:
        logger.error(f"Failed to fetch history: {e}")
        return JSONResponse({'history': [], 'count': 0, 'error': str(e)})

# ============================================
# Streaming Endpoints
# ============================================

@app.get('/stream/{file_path:path}')
async def stream_media(file_path: str, request: Request):
    """Stream media files with range request support"""
    full_path = os.path.join(DATA_DIR, file_path)
    client_ip = request.client.host if request.client else "unknown"

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail='File not found')

    file_size = os.path.getsize(full_path)
    mime_type = get_mime_type(full_path)
    file_name = os.path.basename(file_path)
    file_type = get_file_type(file_name)

    # Track view on initial request
    range_header = request.headers.get('range')
    if not range_header or range_header.startswith('bytes=0-'):
        track_view(client_ip, file_path, file_name, file_type, file_size)

    # Handle range requests
    if range_header:
        try:
            range_str = range_header.replace('bytes=', '')
            range_parts = range_str.split('-')
            start = int(range_parts[0]) if range_parts[0] else 0
            end = int(range_parts[1]) if len(range_parts) > 1 and range_parts[1] else file_size - 1

            start = max(0, min(start, file_size - 1))
            end = min(end, file_size - 1)
            content_length = end - start + 1

            with open(full_path, 'rb') as f:
                f.seek(start)
                data = f.read(content_length)

            headers = {
                'Content-Range': f'bytes {start}-{end}/{file_size}',
                'Accept-Ranges': 'bytes',
                'Content-Length': str(content_length),
                'Content-Type': mime_type,
            }

            return Response(content=data, status_code=206, headers=headers, media_type=mime_type)
        except Exception as e:
            logger.error(f"Range request error: {e}")
            raise HTTPException(status_code=416, detail='Range not satisfiable')

    return FileResponse(
        full_path,
        media_type=mime_type,
        headers={'Accept-Ranges': 'bytes', 'Content-Length': str(file_size)}
    )

@app.get('/transcode/{file_path:path}')
async def transcode_stream(file_path: str, request: Request, start_time: float = 0):
    """Transcode video on-the-fly with seeking support"""
    full_path = os.path.join(DATA_DIR, file_path)
    client_ip = request.client.host if request.client else "unknown"

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail='File not found')

    video_info = get_video_info(full_path)
    if not video_info:
        raise HTTPException(status_code=500, detail='Could not read video metadata')

    # Track view on initial request
    if start_time == 0:
        file_name = os.path.basename(file_path)
        file_type = get_file_type(file_name)
        file_size = os.path.getsize(full_path)
        track_view(client_ip, file_path, file_name, file_type, file_size)

    cmd = ['ffmpeg']
    if start_time > 0:
        cmd.extend(['-ss', str(start_time)])

    cmd.extend([
        '-i', full_path,
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-crf', '23',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-movflags', 'frag_keyframe+empty_moov+faststart',
        '-f', 'mp4',
        'pipe:1'
    ])

    async def transcode_generator():
        process = None
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=65536)
            loop = asyncio.get_event_loop()

            while True:
                chunk = await loop.run_in_executor(None, process.stdout.read, 65536)
                if not chunk:
                    break
                yield chunk

            process.wait()
        except (GeneratorExit, asyncio.CancelledError):
            if process and process.poll() is None:
                process.kill()
                process.wait()
            raise
        except Exception as e:
            logger.error(f"Transcode error: {e}")
            if process and process.poll() is None:
                process.kill()
        finally:
            if process and process.poll() is None:
                process.kill()

    return StreamingResponse(
        transcode_generator(),
        media_type='video/mp4',
        headers={
            'X-Duration': str(video_info['duration']),
            'X-Start-Time': str(start_time),
            'Cache-Control': 'no-cache',
        }
    )

# ============================================
# Other Endpoints
# ============================================

@app.get('/preview/{file_path:path}')
async def preview_text(file_path: str):
    """Preview text file content"""
    full_path = os.path.join(DATA_DIR, file_path)

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail='File not found')

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read(100000)
        return Response(content=content, media_type='text/plain')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Cannot read file: {str(e)}')

@app.post('/download')
async def download_file(request: Request):
    """Download file or directory as zip"""
    form_data = await request.form()
    file_path = form_data["file_path"]
    file_name = form_data["file_name"]

    if os.path.isfile(file_path):
        return FileResponse(file_path, filename=file_name)
    elif os.path.isdir(file_path):
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, file_name + '.zip')

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(file_path):
                for file in files:
                    file_path_abs = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path_abs, file_path)
                    zipf.write(file_path_abs, arcname=relative_path)

        async def stream_zip():
            with open(zip_path, 'rb') as f:
                while chunk := f.read(4096):
                    yield chunk
            shutil.rmtree(temp_dir, ignore_errors=True)

        return StreamingResponse(
            stream_zip(),
            media_type='application/zip',
            headers={'Content-Disposition': f'attachment; filename="{file_name}.zip"'}
        )
    else:
        raise HTTPException(status_code=404, detail='File or directory not found')

@app.get('/')
@app.get('/{directories:path}')
def browse_directory(request: Request, directories: str = ''):
    """Browse directory and list files"""
    browse_directory_path = os.path.join(DATA_DIR, directories)

    if not os.path.isdir(browse_directory_path):
        raise HTTPException(status_code=404, detail='Directory not found')

    files = []
    subdirectories = []

    for entry in os.scandir(browse_directory_path):
        stat_info = entry.stat()

        if entry.is_file():
            relative_path = os.path.relpath(entry.path, DATA_DIR)
            files.append({
                'name': entry.name,
                'size': stat_info.st_size,
                'path': entry.path,
                'relative_path': relative_path,
                'type': get_file_type(entry.name),
                'modified': stat_info.st_mtime
            })
        else:
            subdirectories.append({
                'name': entry.name,
                'path': entry.path,
                'modified': stat_info.st_mtime
            })

    subdirectories.sort(key=lambda x: x['name'].lower())
    files.sort(key=lambda x: x['name'].lower())

    path_parts = [p for p in directories.split('/') if p]
    breadcrumbs = [{'name': 'Home', 'path': ''}]
    current_path = ''
    for part in path_parts:
        current_path += '/' + part
        breadcrumbs.append({'name': part, 'path': current_path.lstrip('/')})

    return templates.TemplateResponse(
        "file_browser.html",
        {
            "request": request,
            "files": files,
            "directories": subdirectories,
            "breadcrumbs": breadcrumbs,
            "current_path": directories
        }
    )
