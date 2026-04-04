import json

import pika

RABBITMQ_HOST = "localhost"
QUEUE_NAME = "cola_imagenes"

_connection = None
_channel = None


def _get_channel():
    global _connection, _channel
    if _connection is None or _connection.is_closed:
        _connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        _channel = _connection.channel()
        _channel.queue_declare(queue=QUEUE_NAME, durable=True)
    return _channel


def publicar_tarea(data: dict) -> None:
    channel = _get_channel()
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=json.dumps(data),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    print(f"[RabbitMQ] Tarea publicada: {data['id_imagen'][:8]}...")
