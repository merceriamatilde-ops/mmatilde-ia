from typing import Literal, Optional
from pydantic import BaseModel, Field


class ResumenProyecto(BaseModel):
    proyecto: str = ""
    tecnica: Optional[str] = None
    detalles: list[str] = Field(default_factory=list)


class ProgresoConsulta(BaseModel):
    confirmado: list[str] = Field(default_factory=list)
    falta: list[str] = Field(default_factory=list)
    pasos_restantes: int = 1
    ultimo_paso: bool = False


class OpcionPregunta(BaseModel):
    id: str
    label: str


class Pregunta(BaseModel):
    id: str
    pregunta: str
    opciones: list[OpcionPregunta]


class Insumo(BaseModel):
    descripcion: str
    termino_busqueda: str


class ResultadoEstimacion(BaseModel):
    tecnica_detectada: str
    insumos: list[Insumo]
    nota: str = ""
    completitud: Literal["exacta", "aproximada"] = "exacta"
    supuestos: list[str] = Field(default_factory=list)
    chequeos: list[str] = Field(default_factory=list)


class ProductoSugerido(BaseModel):
    id: int
    slug: str
    nombre: str
    categoria: str
    imagen_url: Optional[str] = None
    termino_relacionado: str


class ConsultaContexto(BaseModel):
    descripcion_inicial: str = ""
    respuestas: list[dict] = Field(default_factory=list)
    notas_adicionales: list[str] = Field(default_factory=list)


class ConsultaResponse(BaseModel):
    estado: Literal["preguntando", "listo"]
    mensaje: str
    progreso: ProgresoConsulta
    resumen: ResumenProyecto
    preguntas: list[Pregunta] = Field(default_factory=list)
    resultado: Optional[ResultadoEstimacion] = None
    productos_sugeridos: list[ProductoSugerido] = Field(default_factory=list)
