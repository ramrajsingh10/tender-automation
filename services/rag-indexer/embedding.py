from __future__ import annotations

import logging
import os
from typing import Iterable, List

import numpy as np
from google.cloud import aiplatform
import vertexai
from vertexai.language_models import TextEmbeddingModel

logger = logging.getLogger(__name__)


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
        embeddings = self._model.get_embeddings(texts)
        return [embedding.values for embedding in embeddings]


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

        matching_datapoints = []
        namespace = aiplatform.matching_engine
        for point in datapoints:
            vector = point["feature_vector"]
            matching_datapoints.append(
                namespace.Datapoint(
                    datapoint_id=point["datapoint_id"],
                    feature_vector=vector,
                    restricts=point.get("restricts"),
                    crowding_tag=point.get("crowding_tag"),
                )
            )
        self._endpoint.upsert_datapoints(index_id=self._index_id, datapoints=matching_datapoints)
