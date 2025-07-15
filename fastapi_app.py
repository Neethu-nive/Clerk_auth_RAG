from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware  # <-- Add this import
from pydantic import BaseModel
import jwt
import os

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = os.getenv("JWT_SECRET", "sk_test_DpURagihAWm783nzCdBkFgTNowyraAHjkk3CvupnIB")
ALGORITHM = "HS256"
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

class ChatRequest(BaseModel):
    question: str

@app.get("/protected")
def protected_route(payload: dict = Depends(verify_token)):
    return {"message": "Access granted", "user_id": payload.get("sub")}

@app.post("/api/chat")
def chat_endpoint(req: ChatRequest, payload: dict = Depends(verify_token)):
    # TODO: Replace this stub with your RAG model pipeline call.
    return {"answer": f"🔁 Echo: {req.question}"}
