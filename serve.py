"""Start the Todo API with one command.

    python serve.py

The server listens on port 8000. Set PORT to use another port, for example
PORT=9000 python serve.py. Set HOST to listen on another interface (default 127.0.0.1).
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
