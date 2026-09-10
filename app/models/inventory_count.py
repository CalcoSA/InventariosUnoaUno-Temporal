from dataclasses import dataclass


@dataclass
class InventoryCount:
    item: str
    cerrado: float
    abierto: float
    factor: float

    @property
    def conteo_fisico(self):
        return self.cerrado * self.factor + self.abierto
