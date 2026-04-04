from pydantic import BaseModel


class LoteResponse(BaseModel):
    id_lote: str
    estado: str


class LoteEstadoResponse(BaseModel):
    id_lote: str
    estado: str
    total: int
    completadas: int
    progreso: float
