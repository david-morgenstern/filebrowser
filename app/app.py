from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

app = FastAPI()

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory="/app/templates")


@app.post('/download')
async def download_file(request: Request):
    form_data = await request.form()
    file_path = form_data["file_path"]
    file_name = form_data["file_name"]

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail='File not found')

    return FileResponse(file_path, filename=file_name)


@app.get('/')
@app.get('/{directories:path}')
def browse_directory(request: Request, directories: str):
    browse_directory_path = '/app/data' + directories
    if not os.path.isdir(browse_directory_path):
        raise HTTPException(status_code=500, detail='Invalid directory path')

    files = []
    directories = []
    for entry in os.scandir(browse_directory_path):
        if entry.is_file():
            file_data = {
                'name': entry.name,
                'size': entry.stat().st_size,
                'path': entry.path
            }
            files.append(file_data)
        else:
            directories.append(entry)
    return templates.TemplateResponse("file_browser.html",
                                      {"request": request, "files": files, "directories": directories})
