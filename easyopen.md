### 1. Backend starten
```bash
cd backend
docker compose up -d

---- still BE :
cd backend
uvicorn app.main:app --reload --port 8080


### . Frontend starten

cd frontend
npm install   # nur beim ersten Mal
npm run dev

###Install all PIP : 

pip install -r requirements.txt