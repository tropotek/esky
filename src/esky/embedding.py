from functools import cached_property

from fastembed import TextEmbedding

from esky.config import EMBED_DIM


class Embedder:
    """In-process ONNX embeddings.

    Deliberately not an HTTP call: embeddings sit on the write path, and a
    write must not fail because an external service is down (spec 3.3).
    """

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    @cached_property
    def _model(self) -> TextEmbedding:
        return TextEmbedding(model_name=self.model_name)

    @property
    def dim(self) -> int:
        return EMBED_DIM

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = [v.tolist() for v in self._model.embed(texts)]
        for v in vectors:
            if len(v) != EMBED_DIM:
                raise ValueError(
                    f"{self.model_name} returned dim {len(v)}, expected {EMBED_DIM}"
                )
        return vectors
