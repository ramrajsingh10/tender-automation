from __future__ import annotations

import os
from typing import Optional

from google.auth import exceptions as auth_exceptions
from google.cloud import firestore

_firestore_client: Optional[firestore.Client] = None


def get_firestore_client() -> firestore.Client:
    """Return a cached Firestore client, instantiating it lazily."""
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client

    project_id = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")

    try:
        _firestore_client = firestore.Client(project=project_id or None)
    except auth_exceptions.DefaultCredentialsError as exc:
        raise RuntimeError(
            "Firestore credentials not configured. Set GOOGLE_APPLICATION_CREDENTIALS or "
            "point to the Firestore emulator via FIRESTORE_EMULATOR_HOST."
        ) from exc

    return _firestore_client
