import json
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from . import models, schemas, crud
from .database import SessionLocal, engine
from fastapi.middleware.cors import CORSMiddleware
from .celery_app import celery_app
from .tasks import fetch_weather_data
import json
from celery import chain  
import asyncio
import logging
from sqlalchemy import func

# Crear las tablas de la base de datos
models.Base.metadata.create_all(bind=engine)

app = FastAPI()


# Configurar orígenes permitidos
origins = [
    "http://localhost:3000",  # origen de tu frontend en desarrollo
    "https://next-react-asj.vercel.app",  # origen de tu frontend en producción
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dependencia para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
async def health_check():
    return "The healt check is successful!"

@app.get("/cars", response_model=List[schemas.Car])
def read_cars(skip: int = 0, limit: int = 10, brand: Optional[str] = None, subsidiaryName: Optional[str] = None, db: Session = Depends(get_db)):
    logger.info(f"Query params - brand: {brand}, subsidiary_name: {subsidiaryName}")
    
    query = db.query(models.Car).join(models.Subsidiary)
    
    if brand:
        query = query.filter(func.lower(models.Car.brand) == func.lower(brand))
    if subsidiaryName:
        query = query.filter(func.lower(models.Subsidiary.name) == func.lower(subsidiaryName))
    
    cars = query.offset(skip).limit(limit).all()
    
    logger.info(f"Number of cars found: {len(cars)}")
    return cars

@app.post("/cars", response_model=schemas.Car)
def create_car(car: schemas.CarCreate, db: Session = Depends(get_db)):
    return crud.create_car(db=db, car=car)


app.state.fetch_weather_task = None

@app.post("/fetch-weather")
async def fetch_weather():
    if not app.state.fetch_weather_task:
        app.state.fetch_weather_task = asyncio.create_task(periodic_fetch_weather())
    return {"status": "Task initiated"}

# Función asincrónica para ejecutar el endpoint periódicamente
async def periodic_fetch_weather():
    while True:
        await asyncio.sleep(5)  # Esperar 5 segundos
        task_chain = chain(fetch_weather_data.s())
        task_chain.apply_async()


@app.on_event("shutdown")
async def shutdown_event():
    if app.state.fetch_weather_task:
        app.state.fetch_weather_task.cancel()
        try:
            await app.state.fetch_weather_task
        except asyncio.CancelledError:
            pass


""" # Iniciar la aplicación
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) """