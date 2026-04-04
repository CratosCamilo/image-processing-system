class ServidorCoordinador:
    def iniciar_procesamiento(self, id_lote: str) -> None:
        print(f"[Coordinador] Lote recibido: {id_lote} — en cola para procesamiento.")
