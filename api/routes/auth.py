from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from services.auth_service import autenticar_usuario, crear_token

router = APIRouter(prefix="/auth", tags=["autenticación"])


class LoginRequest(BaseModel):
    correo: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión",
    description=(
        "Autentica con correo y contraseña. "
        "Retorna un Bearer token JWT que debe incluirse en el header "
        "`Authorization: Bearer <token>` para los endpoints protegidos."
    ),
)
async def login(body: LoginRequest):
    usuario = autenticar_usuario(body.correo, body.password)
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = crear_token(usuario["id_usuario"], usuario["correo"])
    return TokenResponse(access_token=token, token_type="bearer")
