from dataclasses import dataclass, asdict


@dataclass
class Product:
    id: int
    categoria: str
    item: str
    producto: str
    udm: str
    factor: float

    def to_dict(self):
        return asdict(self)
