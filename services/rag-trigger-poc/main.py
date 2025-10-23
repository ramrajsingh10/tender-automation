'''Cloud Function to trigger RAG indexing when a file is uploaded to GCS.'''

import functions_framework
from google.cloud import aiplatform

# --- Configuration (Hardcoded for PoC) ---
PROJECT_ID = "tender-automation-1008"
LOCATION = "us-east4"
CORPUS_ID = "6917529027641081856"


@functions_framework.cloud_event
def trigger_rag_indexing(cloud_event):
    '''
    This function is triggered by a CloudEvent from Google Cloud Storage.
    It imports the newly uploaded file into the Vertex AI RAG Corpus.
    '''
    print(f"Received event: {cloud_event}")

    data = cloud_event.data
    bucket = data.get("bucket")
    name = data.get("name")

    if not bucket or not name:
        print("Error: Malformed GCS event data.")
        return

    print(f"Processing file: {name} from bucket: {bucket}")

    # Initialize the Vertex AI client
    aiplatform.init(project=PROJECT_ID, location=LOCATION)

    # Construct the GCS URI of the file
    gcs_uri = f"gs://{bucket}/{name}"

    try:
        # Import the file into the RAG corpus
        print(f"Importing {gcs_uri} into RAG Corpus {CORPUS_ID}...")
        corpus = aiplatform.gapic.RagCorpus(name=f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{CORPUS_ID}")
        
        # The import is an async operation, but for a Cloud Function,
        # we can just kick it off.
        aiplatform.gapic.VertexRagDataServiceClient().import_rag_files(
            parent=corpus.name,
            import_rag_files_config={
                "gcs_source": {"uris": [gcs_uri]},
            }
        )

        print(f"Successfully started import job for {gcs_uri}")

    except Exception as e:
        print(f"Error importing file to RAG Engine: {e}")
        # Optionally, you could move the file to an 'error' folder here
        raise
