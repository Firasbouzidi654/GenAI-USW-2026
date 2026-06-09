cd backend
docker compose up -d
---- still BE :

uvicorn app.main:app --reload --port 8080


### 7. Frontend starten

cd frontend
npm install   # nur beim ersten Mal
npm run dev

