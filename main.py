"""Root entrypoint for deployment platforms (Render, Railway, Heroku, etc.)."""
import os
import sys
from pathlib import Path

# Add workspace root and backend directory to sys.path
root_dir = Path(__file__).resolve().parent
backend_dir = root_dir / "backend"

for p in (str(root_dir), str(backend_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.app.main import app, create_app  # noqa: F401

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port)
