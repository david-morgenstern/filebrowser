import shutil
import tempfile
import zipfile

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

from starlette.responses import StreamingResponse

app = FastAPI()

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.mount("/data", StaticFiles(directory="/app/data"), name="data")
templates = Jinja2Templates(directory="/app/templates")


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
def browse_directory(request: Request, directories: str):
    show_pictures = False
    if directories.endswith("pictures"):
        directories = directories.rstrip("pictures")
        directories = directories.rstrip("/")
        show_pictures = True

    browse_directory_path = '/app/data' + directories
    if not os.path.isdir(browse_directory_path):
        raise HTTPException(status_code=500, detail='Invalid directory path')

    picture_extensions = (".jpg", ".jpeg", ".JPG")
    picture_files = []

    if show_pictures:
        for entry in os.scandir(browse_directory_path):
            if entry.is_file() and entry.name.lower().endswith(picture_extensions):
                file_data = {
                    'name': "/".join(entry.path.split("/")[3:]),
                    'path': entry.path
                }
                picture_files.append(file_data)
        return templates.TemplateResponse(
            "picture_viewer.html",
            {"request": request, "picture_files": picture_files, "current_page": "picture_viewer"}
        )

    files = []
    subdirectories = []
    for entry in os.scandir(browse_directory_path):
        if entry.is_file():
            file_data = {
                'name': entry.name,
                'size': entry.stat().st_size,
                'path': entry.path
            }
            files.append(file_data)
        else:
            subdirectories.append(entry)
    return templates.TemplateResponse(
        "file_browser.html",
        {"request": request, "files": files, "directories": subdirectories, "current_page": "file_browser"}
    )