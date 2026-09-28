import os
import time
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict

CONSUL_URL = os.getenv("CONSUL_URL", "http://consul:8500/v1/agent/service")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "catalog-default")
PORT = int(os.getenv("PORT", "8001"))

products_db: Dict[int, dict] = {
    1: {"name": "Laptop", "price": 999.99},
    2: {"name": "Smartphone", "price": 499.99}
}
current_id = 2

class ProductSchema(BaseModel):
    name: str
    price: float

async def lifespan(app: FastAPI):
    # Авто-регистрация инстанса в Consul
    registration_data = {
        "Name": "catalog-service",
        "ID": INSTANCE_NAME,
        "Address": INSTANCE_NAME, # Имя контейнера совпадает с ID в сети Docker
        "Port": PORT
    }
    time.sleep(3)
    async with httpx.AsyncClient() as client:
        try:
            await client.put(f"{CONSUL_URL}/register", json=registration_data)
            print(f"Registered {INSTANCE_NAME} in Consul")
        except Exception as e:
            print(f"Consul reg error: {e}")
            
    yield
    
    # Авто-дерегистрация инстанса
    async with httpx.AsyncClient() as client:
        try:
            await client.put(f"{CONSUL_URL}/deregister/{INSTANCE_NAME}")
            print(f"Deregistered {INSTANCE_NAME} from Consul")
        except Exception as e:
            print(f"Consul dereg error: {e}")

app = FastAPI(lifespan=lifespan)

@app.get("/products")
async def get_products():
    # Обязательно возвращаем instance_id для демонстрации балансировки!
    return {
        "products": list(products_db.values()),
        "instance_id": INSTANCE_NAME
    }

@app.post("/products", status_code=201)
async def create_product(product: ProductSchema):
    global current_id
    current_id += 1
    products_db[current_id] = product.model_dump()
    return {"id": current_id, "product": products_db[current_id]}

@app.put("/products/{product_id}")
async def update_product(product_id: int, product: ProductSchema):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Product not found")
    products_db[product_id] = product.model_dump()
    return {"id": product_id, "product": products_db[product_id]}

@app.delete("/products/{product_id}")
async def delete_product(product_id: int):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Product not found")
    del products_db[product_id]
    return {"message": f"Product {product_id} deleted"}