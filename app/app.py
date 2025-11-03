import shutil
import tempfile
import zipfile
import mimetypes
import logging
import asyncio
from pathlib import Path
import sqlite3
from datetime import datetime
from contextlib import contextmanager
import subprocess
import json

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

from starlette.responses import StreamingResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database file location (in separate volume)
DB_PATH = '/app/db/filebrowser_history.db'
DB_DIR = '/app/db'

@contextmanager
def get_db():
    """Context manager for database connections"""
    # Ensure db directory exists
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
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_ip_watched
                ON watch_history(ip_address, last_watched DESC)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_file_watched
                ON watch_history(file_path, last_watched DESC)
            ''')
            logger.info("Database initialized successfully at " + DB_PATH)
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

def track_view(ip_address: str, file_path: str, file_name: str, file_type: str, file_size: int):
    """Track a file view in the database"""
    try:
        with get_db() as conn:
            # Check if this IP has watched this file before
            existing = conn.execute(
                'SELECT id, view_count FROM watch_history WHERE ip_address = ? AND file_path = ?',
                (ip_address, file_path)
            ).fetchone()

            if existing:
                # Update existing record
                conn.execute(
                    'UPDATE watch_history SET last_watched = ?, view_count = ? WHERE id = ?',
                    (datetime.now(), existing['view_count'] + 1, existing['id'])
                )
            else:
                # Insert new record
                conn.execute(
                    '''INSERT INTO watch_history
                       (ip_address, file_path, file_name, file_type, file_size, first_watched, last_watched)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (ip_address, file_path, file_name, file_type, file_size, datetime.now(), datetime.now())
                )
    except Exception as e:
        logger.error(f"Failed to track view: {e}")

app = FastAPI()

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory="/app/templates")

# File type categories
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg')
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.wmv', '.m4v')
TEXT_EXTENSIONS = ('.txt', '.md', '.log', '.json', '.xml', '.csv', '.py', '.js', '.html', '.css', '.sh', '.yml', '.yaml', '.ini', '.conf')
AUDIO_EXTENSIONS = ('.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac')

# Explicit MIME type mappings for audio/video formats
# This ensures browsers get the correct codec information
MIME_TYPE_MAP = {
    # Video formats
    '.mp4': 'video/mp4',
    '.m4v': 'video/mp4',
    '.webm': 'video/webm',
    '.mkv': 'video/x-matroska',
    '.avi': 'video/x-msvideo',
    '.mov': 'video/quicktime',
    '.flv': 'video/x-flv',
    '.wmv': 'video/x-ms-wmv',

    # Audio formats
    '.mp3': 'audio/mpeg',
    '.m4a': 'audio/mp4',
    '.aac': 'audio/aac',
    '.wav': 'audio/wav',
    '.flac': 'audio/flac',
    '.ogg': 'audio/ogg',
    '.oga': 'audio/ogg',
    '.opus': 'audio/opus',
}

def get_mime_type(file_path):
    """Get MIME type with explicit mappings for audio/video formats"""
    ext = os.path.splitext(file_path.lower())[1]

    # Use explicit mapping if available
    if ext in MIME_TYPE_MAP:
        return MIME_TYPE_MAP[ext]

    # Fall back to mimetypes module
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or 'application/octet-stream'

def get_file_type(filename):
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
    else:
        return 'file'

def needs_transcoding(file_path):
    """Check if video needs transcoding based on codec"""
    try:
        # Use ffprobe to get video codec
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-select_streams', 'v:0',
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            logger.error(f"ffprobe failed for {file_path}")
            return False

        data = json.loads(result.stdout)
        if not data.get('streams'):
            return False

        codec = data['streams'][0].get('codec_name', '').lower()
        logger.info(f"Detected codec: {codec} for {file_path}")

        # Codecs that need transcoding (not supported by browsers)
        unsupported = ['xvid', 'divx', 'mpeg4', 'msmpeg4', 'wmv', 'flv1', 'vp6']

        return codec in unsupported
    except Exception as e:
        logger.error(f"Error checking codec: {e}")
        return False


@app.get('/transcode/{file_path:path}')
async def transcode_stream(file_path: str, request: Request):
    """Transcode video on-the-fly to H.264/MP4 for browser compatibility"""
    full_path = os.path.join('/app/data', file_path)
    client_ip = request.client.host if request.client else "unknown"

    logger.info(f"=== TRANSCODE REQUEST ===")
    logger.info(f"Path: {file_path}")
    logger.info(f"Client IP: {client_ip}")

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail='File not found')

    # Track the view
    file_name = os.path.basename(file_path)
    file_type = get_file_type(file_name)
    file_size = os.path.getsize(full_path)
    track_view(client_ip, file_path, file_name, file_type, file_size)

    # ffmpeg command to transcode to H.264/AAC/MP4
    cmd = [
        'ffmpeg',
        '-i', full_path,
        '-c:v', 'libx264',           # H.264 video codec
        '-preset', 'veryfast',        # Fast encoding
        '-crf', '23',                 # Quality (lower = better, 18-28 is good)
        '-c:a', 'aac',                # AAC audio codec
        '-b:a', '128k',               # Audio bitrate
        '-movflags', 'frag_keyframe+empty_moov',  # Enable streaming
        '-f', 'mp4',                  # Output format
        'pipe:1'                      # Output to stdout
    ]

    logger.info(f"Starting transcode: {' '.join(cmd)}")

    async def transcode_generator():
        process = None
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=65536
            )

            logger.info(f"ffmpeg process started: PID {process.pid}")

            loop = asyncio.get_event_loop()

            while True:
                # Read in executor to not block event loop
                chunk = await loop.run_in_executor(None, process.stdout.read, 65536)
                if not chunk:
                    break
                yield chunk

            # Process finished normally
            process.wait()
            if process.returncode != 0:
                error = process.stderr.read().decode('utf-8')
                logger.error(f"ffmpeg error: {error}")
            else:
                logger.info(f"ffmpeg completed successfully")

        except (GeneratorExit, asyncio.CancelledError) as e:
            # Client disconnected
            logger.info(f"Client disconnected, killing ffmpeg process (PID {process.pid if process else 'unknown'})")
            if process and process.poll() is None:
                process.kill()
                process.wait()
            raise
        except Exception as e:
            logger.error(f"Transcode error: {e}")
            if process and process.poll() is None:
                process.kill()
                process.wait()
        finally:
            # Always cleanup
            if process and process.poll() is None:
                logger.info(f"Cleaning up ffmpeg process (PID {process.pid})")
                process.kill()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    logger.error(f"ffmpeg process didn't terminate, force killing")
                    process.kill()

    return StreamingResponse(
        transcode_generator(),
        media_type='video/mp4',
        headers={
            'Accept-Ranges': 'none',  # Can't seek transcoded stream
            'Cache-Control': 'no-cache',
        }
    )


@app.get('/stream/{file_path:path}')
async def stream_media(file_path: str, request: Request):
    """Stream media files with proper range request support for multiple concurrent clients"""
    from starlette.responses import Response

    full_path = os.path.join('/app/data', file_path)

    # Get client IP
    client_ip = request.client.host if request.client else "unknown"

    logger.info(f"=== STREAM REQUEST ===")
    logger.info(f"Path: {file_path}")
    logger.info(f"Full path: {full_path}")
    logger.info(f"Client IP: {client_ip}")
    logger.info(f"File exists: {os.path.isfile(full_path)}")
    logger.info(f"Range: {request.headers.get('range', 'NO RANGE')}")

    if not os.path.isfile(full_path):
        logger.error(f"FILE NOT FOUND: {full_path}")
        raise HTTPException(status_code=404, detail=f'File not found')

    file_size = os.path.getsize(full_path)
    mime_type = get_mime_type(full_path)
    file_name = os.path.basename(file_path)
    file_type = get_file_type(file_name)

    logger.info(f"File size: {file_size} bytes, MIME: {mime_type}")

    # Get range header
    range_header = request.headers.get('range')

    # Track view only on first request (no range header) or initial range request (starts at 0)
    if not range_header or range_header.startswith('bytes=0-'):
        track_view(client_ip, file_path, file_name, file_type, file_size)
        logger.info(f"Tracked view for {client_ip}")

    # Handle range requests
    if range_header:
        try:
            range_str = range_header.replace('bytes=', '')
            range_parts = range_str.split('-')
            start = int(range_parts[0]) if range_parts[0] else 0
            end = int(range_parts[1]) if len(range_parts) > 1 and range_parts[1] else file_size - 1

            # Clamp values
            start = max(0, min(start, file_size - 1))
            end = min(end, file_size - 1)
            content_length = end - start + 1

            logger.info(f"RANGE: {start}-{end}/{file_size} = {content_length} bytes")

            # Read the file chunk
            with open(full_path, 'rb') as f:
                f.seek(start)
                data = f.read(content_length)

            headers = {
                'Content-Range': f'bytes {start}-{end}/{file_size}',
                'Accept-Ranges': 'bytes',
                'Content-Length': str(content_length),
                'Content-Type': mime_type,
            }

            logger.info(f"Returning 206 with {len(data)} bytes")
            return Response(content=data, status_code=206, headers=headers, media_type=mime_type)

        except Exception as e:
            logger.error(f"RANGE ERROR: {e}")
            raise HTTPException(status_code=416, detail='Range not satisfiable')

    # No range - return full file info with Accept-Ranges
    logger.info(f"NO RANGE - Using FileResponse")

    # Use FileResponse which handles everything including ranges automatically
    return FileResponse(
        full_path,
        media_type=mime_type,
        headers={
            'Accept-Ranges': 'bytes',
            'Content-Length': str(file_size),
        }
    )


@app.get('/mimetype/{file_path:path}')
async def get_file_mimetype(file_path: str):
    """Return the MIME type for a file"""
    full_path = os.path.join('/app/data', file_path)

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail='File not found')

    mime_type = get_mime_type(full_path)
    return JSONResponse({'mimeType': mime_type})


@app.get('/preview/{file_path:path}')
async def preview_text(file_path: str):
    full_path = os.path.join('/app/data', file_path)

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail='File not found')

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read(100000)  # Max 100KB
        return Response(content=content, media_type='text/plain')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Cannot read file: {str(e)}')


@app.post('/download')
async def download_file(request: Request):
    form_data = await request.form()
    file_path = form_data["file_path"]
    file_name = form_data["file_name"]

    if os.path.isfile(file_path):
        return FileResponse(file_path, filename=file_name)
    elif os.path.isdir(file_path):
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, file_name + '.zip')

        async def create_zip():
            print(f"Creating zipfile. {zip_path}")
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(file_path):
                    for file in files:
                        file_path_abs = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path_abs, file_path)
                        zipf.write(file_path_abs, arcname=relative_path)

        await create_zip()

        def cleanup():
            print(f"Removing temp_dir. {temp_dir}")
            shutil.rmtree(temp_dir, ignore_errors=True)

        async def stream_zip():
            with open(zip_path, 'rb') as f:
                while True:
                    data = f.read(4096)
                    if not data:
                        break
                    yield data
            cleanup()

        return StreamingResponse(stream_zip(), media_type='application/zip',
                                 headers={'Content-Disposition': f'attachment; filename="{file_name}.zip"'})

    else:
        raise HTTPException(status_code=404, detail='File or directory not found')


@app.get('/api/history')
async def get_history(request: Request, limit: int = 50):
    """Get watch history for the current user's IP"""
    client_ip = request.client.host if request.client else "unknown"

    try:
        with get_db() as conn:
            rows = conn.execute(
                '''SELECT file_path, file_name, file_type, file_size,
                          first_watched, last_watched, view_count
                   FROM watch_history
                   WHERE ip_address = ?
                   ORDER BY last_watched DESC
                   LIMIT ?''',
                (client_ip, limit)
            ).fetchall()

            history = []
            for row in rows:
                history.append({
                    'file_path': row['file_path'],
                    'file_name': row['file_name'],
                    'file_type': row['file_type'],
                    'file_size': row['file_size'],
                    'first_watched': row['first_watched'],
                    'last_watched': row['last_watched'],
                    'view_count': row['view_count']
                })

            return JSONResponse({'history': history, 'count': len(history)})
    except Exception as e:
        logger.error(f"Failed to fetch history: {e}")
        return JSONResponse({'history': [], 'count': 0, 'error': str(e)})


@app.get('/')
@app.get('/{directories:path}')
def browse_directory(request: Request, directories: str = ''):
    browse_directory_path = os.path.join('/app/data', directories)

    if not os.path.isdir(browse_directory_path):
        raise HTTPException(status_code=404, detail='Directory not found')

    files = []
    subdirectories = []

    for entry in os.scandir(browse_directory_path):
        stat_info = entry.stat()

        if entry.is_file():
            relative_path = os.path.relpath(entry.path, '/app/data')
            file_data = {
                'name': entry.name,
                'size': stat_info.st_size,
                'path': entry.path,
                'relative_path': relative_path,
                'type': get_file_type(entry.name),
                'modified': stat_info.st_mtime
            }
            files.append(file_data)
        else:
            dir_data = {
                'name': entry.name,
                'path': entry.path,
                'modified': stat_info.st_mtime
            }
            subdirectories.append(dir_data)

    # Sort: directories first, then files
    subdirectories.sort(key=lambda x: x['name'].lower())
    files.sort(key=lambda x: x['name'].lower())

    # Create breadcrumbs
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