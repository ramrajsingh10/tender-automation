'''Proof of Concept (PoC) API endpoints for the RAG pipeline.'''

import datetime

from fastapi import APIRouter, HTTPException
from google.cloud import aiplatform, storage
from pydantic import BaseModel

# --- Configuration (Hardcoded for PoC) ---
POC_BUCKET_NAME = "uploadeddocuments"
PROJECT_ID = "tender-automation-1008"
LOCATION = "us-east4"  # The region where the RAG Corpus is.
CORPUS_ID = "2305843009213693952"


poc_router = APIRouter(
    prefix="/api/poc",
    tags=["poc"],
)

# --- Upload Endpoint ---

class UploadURLRequest(BaseModel):
    file_name: str
    tender_no: str
    platform: str

class UploadURLResponse(BaseModel):
    url: str
    gcs_path: str

@poc_router.post("/generate-upload-url", response_model=UploadURLResponse)
def generate_upload_url(request: UploadURLRequest):
    '''Generates a v4 signed URL for uploading a file directly to GCS.'''
    try:
        storage_client = storage.Client()
        blob_name = f"{request.platform}/{request.tender_no}/{request.file_name}"
        bucket = storage_client.bucket(POC_BUCKET_NAME)
        blob = bucket.blob(blob_name)

        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="PUT",
            content_type="application/octet-stream",
        )

        return UploadURLResponse(
            url=url, gcs_path=f"gs://{POC_BUCKET_NAME}/{blob_name}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Chat Endpoint ---

class ChatRequest(BaseModel):
    question: str
    tender_no: str
    platform: str

class ChatResponse(BaseModel):
    answer: str

@poc_router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    '''Receives a question and gets an answer from the RAG Engine.'''
    try:
        aiplatform.init(project=PROJECT_ID, location=LOCATION)

        # The full resource name of the RAG Corpus
        corpus_path = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{CORPUS_ID}"

        # Note: For a more advanced implementation, you could use the tender_no and platform
        # to filter the search within the corpus if you have a large number of files.
        # For this PoC, we will search the entire corpus.
        response = aiplatform.rag.retrieval_augmented_generation(
            question=request.question,
            corpus_path=corpus_path,
        )

        return ChatResponse(answer=response.answer)

    except Exception as e:
        print(f"Error during RAG query: {e}")
        raise HTTPException(status_code=500, detail=f"Error querying RAG Engine: {e}")
