from dataclasses import dataclass, asdict


@dataclass
class InventoryResult:
    registros: int
    correcto: bool = True
    mensaje: str = 'Inventario guardado correctamente.'

    def to_dict(self):
        return asdict(self)
