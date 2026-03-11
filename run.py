import uvicorn
from app.core.database import init_db

if __name__ == "__main__":
    print("🚀 Starting Lektes API...")
    init_db()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
