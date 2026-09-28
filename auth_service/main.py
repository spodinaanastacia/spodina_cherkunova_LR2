import os
import time
import httpx
import jwt
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from passlib.context import CryptContext

CONSUL_URL = os.getenv("CONSUL_URL", "http://consul:8500/v1/agent/service")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "auth-service")
PORT = int(os.getenv("PORT", "8000"))

SECRET_KEY = "super-secret-key-for-lab"
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Временное хранилище (in-memory словарь)
users_db = {}

class UserSchema(BaseModel):
    username: str
    password: str

async def lifespan(app: FastAPI):
    # Авто-регистрация в Consul при старте контейнера
    registration_data = {
        "Name": "auth-service",
        "ID": INSTANCE_NAME,
        "Address": "auth", 
        "Port": PORT
    }
    time.sleep(3) # Даем Consul время подняться
    async with httpx.AsyncClient() as client:
        try:
            await client.put(f"{CONSUL_URL}/register", json=registration_data)
            print(f"Registered {INSTANCE_NAME} in Consul")
        except Exception as e:
            print(f"Consul reg error: {e}")
    
    yield # Здесь микросервис работает
    
    # Авто-дерегистрация при остановке контейнера
    async with httpx.AsyncClient() as client:
        try:
            await client.put(f"{CONSUL_URL}/deregister/{INSTANCE_NAME}")
            print(f"Deregistered {INSTANCE_NAME} from Consul")
        except Exception as e:
            print(f"Consul dereg error: {e}")

app = FastAPI(lifespan=lifespan)

@app.post("/register")
async def register(user: UserSchema):
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="User already exists")
    users_db[user.username] = pwd_context.hash(user.password)
    return {"message": "User registered successfully"}

@app.post("/login")
async def login(user: UserSchema):
    hashed_pwd = users_db.get(user.username)
    if not hashed_pwd or not pwd_context.verify(user.password, hashed_pwd):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = jwt.encode({"sub": user.username}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

@app.get("/me")
async def get_me(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "status": "active", "instance": INSTANCE_NAME}
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
