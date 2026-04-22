import json

import aio_pika
from aio_pika.abc import AbstractRobustConnection

RABBITMQ_URL = "amqp://guest:guest@localhost/"
QUEUE_NAME = "cola_imagenes"


async def conectar() -> AbstractRobustConnection:
    """
    Crea una conexión robusta a RabbitMQ y pre-declara la cola.
    Llamar una sola vez en el startup de la app (main.py lifespan).
    connect_robust reconecta automáticamente si RabbitMQ cae.
    """
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection.channel() as channel:
        await channel.declare_queue(QUEUE_NAME, durable=True)
    return connection


async def publicar_tarea(connection: AbstractRobustConnection | None, data: dict) -> None:
    """
    Publica un mensaje en la cola. Abre un canal por publicación y lo cierra al terminar.
    Es seguro llamar concurrentemente desde múltiples coroutines.
    """
    if connection is None:
        print(f"[RabbitMQ] Conexion no disponible, tarea descartada: {data.get('id_imagen', '')[:8]}")
        return
    async with connection.channel() as channel:
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=QUEUE_NAME,
        )
    print(f"[RabbitMQ] Tarea publicada: {data['id_imagen'][:8]}...")
