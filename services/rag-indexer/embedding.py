from __future__ import annotations

import logging
import os
from typing import Iterable, List

import vertexai
from google.cloud import aiplatform
from google.cloud.aiplatform_v1.types import IndexDatapoint
from vertexai.language_models import TextEmbeddingModel

logger = logging.getLogger(__name__)


_EMBED_MAX_CHARS = 1500


class EmbeddingClient:
    def __init__(self, *, project: str, location: str, model_name: str = "text-embedding-005") -> None:
        self._project = project
        self._location = location
        self._model_name = model_name
        vertexai.init(project=project, location=location)
        self._model = TextEmbeddingModel.from_pretrained(model_name)

    def embed(self, texts: Iterable[str]) -> List[List[float]]:
        texts = list(texts)
        if not texts:
            return []
        embeddings: list[list[float]] = []
        for text in texts:
            text = text or ""
            if not text.strip():
                embeddings.append([])
                continue

            slices = [text[i : i + _EMBED_MAX_CHARS] for i in range(0, len(text), _EMBED_MAX_CHARS)]
            slice_vectors: list[list[float]] = []
            for chunk in slices:
                response = self._model.get_embeddings([chunk])
                slice_vectors.append(response[0].values)

            if not slice_vectors:
                embeddings.append([])
                continue

            vector_length = len(slice_vectors[0])
            averaged = [0.0] * vector_length
            for vector in slice_vectors:
                for idx, value in enumerate(vector):
                    averaged[idx] += value
            averaged = [value / len(slice_vectors) for value in averaged]
            embeddings.append(averaged)
        return embeddings


class VectorIndexClient:
    def __init__(self, *, project: str, location: str, index_endpoint_id: str, index_id: str) -> None:
        aiplatform.init(project=project, location=location)
        endpoint_path = aiplatform.gapic.IndexEndpointServiceClient.index_endpoint_path(
            project=project,
            location=location,
            index_endpoint=index_endpoint_id,
        )
        self._endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=endpoint_path)
        self._index_id = index_id

    def upsert(self, datapoints: Iterable[dict]) -> None:
        datapoints = list(datapoints)
        if not datapoints:
            return

        matching_datapoints: list[IndexDatapoint] = []
        for point in datapoints:
            restrict_entries = []
            for entry in point.get("restricts", []):
                restrict_entries.append(
                    IndexDatapoint.RestrictEntry(
                        namespace=entry.get("namespace", ""),
                        allow_list=entry.get("allowList", []),
                        deny_list=entry.get("denyList", []),
                    )
                )

            matching_datapoints.append(
                IndexDatapoint(
                    datapoint_id=point["datapoint_id"],
                    feature_vector=point["feature_vector"],
                    restricts=restrict_entries,
                    crowding_tag=point.get("crowding_tag"),
                )
            )

        self._endpoint.upsert_datapoints(index_id=self._index_id, datapoints=matching_datapoints)
