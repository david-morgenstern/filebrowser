import shutil
import tempfile
import zipfile
import mimetypes
import logging
import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

from starlette.responses import StreamingResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

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


@app.get('/stream/{file_path:path}')
async def stream_media(file_path: str, request: Request):
    """Stream media files with proper range request support for multiple concurrent clients"""
    from starlette.responses import Response

    full_path = os.path.join('/app/data', file_path)

    logger.info(f"=== STREAM REQUEST ===")
    logger.info(f"Path: {file_path}")
    logger.info(f"Full path: {full_path}")
    logger.info(f"File exists: {os.path.isfile(full_path)}")
    logger.info(f"Range: {request.headers.get('range', 'NO RANGE')}")

    if not os.path.isfile(full_path):
        logger.error(f"FILE NOT FOUND: {full_path}")
        raise HTTPException(status_code=404, detail=f'File not found')

    file_size = os.path.getsize(full_path)
    mime_type = get_mime_type(full_path)

    logger.info(f"File size: {file_size} bytes, MIME: {mime_type}")

    range_header = request.headers.get('range')

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