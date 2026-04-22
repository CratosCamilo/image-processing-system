import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from db.database import get_cursor

SECRET_KEY = os.getenv("SECRET_KEY", "imagen_processing_secret_2026_sd")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HORAS = 24

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verificar_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def crear_token(id_usuario: int, correo: str) -> str:
    expira = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HORAS)
    return jwt.encode(
        {"sub": correo, "id": id_usuario, "exp": expira},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def _obtener_usuario_por_correo(correo: str) -> Optional[dict]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id_usuario, correo, password_hash FROM usuario WHERE correo = %s",
            (correo,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def autenticar_usuario(correo: str, password: str) -> Optional[dict]:
    usuario = _obtener_usuario_por_correo(correo)
    if not usuario or not verificar_password(password, usuario["password_hash"]):
        return None
    return usuario


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Debe iniciar sesión primero",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        correo: str = payload.get("sub")
        id_usuario: int = payload.get("id")
        if correo is None or id_usuario is None:
            raise ValueError("payload incompleto")
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado — inicie sesión nuevamente con POST /auth/login",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"id_usuario": id_usuario, "correo": correo}
