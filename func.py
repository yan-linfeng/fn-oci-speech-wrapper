import io
import os
import oci
import time
import json
import datetime
from fdk import response

COMPARTMENT_ID = os.getenv("COMPARTMENT_ID")
OBJECT_STORAGE_BUCKET = os.getenv("OBJECT_STORAGE_BUCKET")
JOB_PREFIX = "STT"
NAMESPACE = ""
SIGNER = oci.auth.signers.get_resource_principals_signer()

def to_dict(obj):
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    elif hasattr(obj, "__dict__"):
        return to_dict(obj.__dict__)
    elif isinstance(obj, list):
        return [to_dict(item) for item in obj]
    else:
        return obj

def handler(ctx, data: io.BytesIO = None):
    try:
        body = json.loads(data.getvalue())
        action = body["action"]
        if action == "create_job":
            return create_job(ctx, body)
        elif action == "query_job":
            return query_job(ctx, body)
        elif action == "get_result":
            return get_result(ctx, body)
        return response.Response(ctx, response_data=json.dumps({"error": "Invalid action"}), headers={"Content-Type": "application/json"})
    except Exception as e:
        return response.Response(ctx, response_data=json.dumps({"error": str(e)}), headers={"Content-Type": "application/json"})

def getSpeechClient():
    return oci.ai_speech.AIServiceSpeechClient(config={}, signer=SIGNER)

def get_namespace():
    global NAMESPACE
    if NAMESPACE == "":
        client = oci.object_storage.ObjectStorageClient(config={}, signer=SIGNER)
        NAMESPACE = client.get_namespace().data
    return NAMESPACE

def get_object(bucketName, objectName):
    client = oci.object_storage.ObjectStorageClient(config={}, signer=SIGNER)
    print("INFO: object_storage_client initialized")
    namespace = get_namespace()
    try:
        print("Searching for bucket and object", flush=True)
        obj = client.get_object(namespace, bucketName, objectName)
        print("found object", flush=True)
        if obj.status == 200:
            print("Success: The object " + objectName + " was retrieved with the content: " + obj.data.text, flush=True)
            return obj.data.text
        else:
            return "Failed: The object " + objectName + " could not be retrieved."
    except Exception as e:
        return "Failed: " + str(e)

def get_formatted_current_time():
    now = datetime.datetime.now()
    return now.strftime("%Y_%m_%d_%H%M_%S_%f")[:-3]

def create_job(ctx, body):
    try:
        file_name = body["file_name"]
        language_code = body["language_code"]
        print("INFO: file_name parsed as {}, bucket parsed as {}".format(file_name, OBJECT_STORAGE_BUCKET), flush=True)

        ai_client = getSpeechClient()
        print("INFO: ai_client initialized")

        formatted_time = get_formatted_current_time()
        display_name = f"stt-job-{formatted_time}"
        description = f"stt-job-{formatted_time}"
        namespace = get_namespace()
        file_names = [file_name]

        MODEL_DETAILS = oci.ai_speech.models.TranscriptionModelDetails(
            model_type="WHISPER_MEDIUM",
            domain="GENERIC",
            language_code=language_code,
            transcription_settings=oci.ai_speech.models.TranscriptionSettings(
                diarization=oci.ai_speech.models.Diarization(
                    is_diarization_enabled=False
                )
            )
        )

        INPUT_LOCATION = oci.ai_speech.models.ObjectListInlineInputLocation(
            location_type="OBJECT_LIST_INLINE_INPUT_LOCATION",
            object_locations=[oci.ai_speech.models.ObjectLocation(
                namespace_name=namespace,
                bucket_name=OBJECT_STORAGE_BUCKET,
                object_names=file_names
            )]
        )

        OUTPUT_LOCATION = oci.ai_speech.models.OutputLocation(
            namespace_name=namespace,
            bucket_name=OBJECT_STORAGE_BUCKET,
            prefix=JOB_PREFIX
        )

        transcription_job_details = oci.ai_speech.models.CreateTranscriptionJobDetails(
            display_name=display_name,
            compartment_id=COMPARTMENT_ID,
            description=description,
            model_details=MODEL_DETAILS,
            input_location=INPUT_LOCATION,
            output_location=OUTPUT_LOCATION
        )

        transcription_job = ai_client.create_transcription_job(create_transcription_job_details=transcription_job_details)
        response_object = {
            "id" : transcription_job.data.id,
            "job_name" : display_name,
            "output_prefix" : transcription_job.data.output_location.prefix
        }
        return response.Response(
            ctx,
            response_data=json.dumps(response_object),
            headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        return response.Response(
            ctx,
            response_data=json.dumps({"error": str(e)}),
            headers={"Content-Type": "application/json"}
        )

def query_job(ctx, body):
    try:
        ai_client = getSpeechClient()
        print("INFO: ai_client initialized")

        job_id = body["job_id"]

        print("***GET TRANSCRIPTION JOB WITH ID***")
        while True:
            try:
                transcription_tasks = ai_client.list_transcription_tasks(job_id)
                if transcription_tasks.data.items:
                    break
            except Exception as e:
                print(e)
                return response.Response(
                    ctx,
                    response_data=json.dumps({"error": str(e)}),
                    headers={"Content-Type": "application/json"}
                )
            time.sleep(1)
        response_object = {
            "lifecycle_state" : transcription_tasks.data.items[0].lifecycle_state 
        }
        return response.Response(
            ctx,
            response_data=json.dumps(response_object),
            headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        return response.Response(
            ctx,
            response_data=json.dumps({"error": str(e)}),
            headers={"Content-Type": "application/json"}
        )

def get_result(ctx, body):
    try:
        output_prefix = body["output_prefix"]
        namespace = get_namespace()
        file_name = body["file_name"]

        output_location = output_prefix + namespace + "_" + OBJECT_STORAGE_BUCKET + "_" + file_name + ".json"
        response_message = get_object(bucketName=OBJECT_STORAGE_BUCKET, objectName=output_location)
        return response.Response(
            ctx,
            response_data = response_message,
            headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        return response.Response(
            ctx,
            response_data=json.dumps({"error": str(e)}),
            headers={"Content-Type": "application/json"}
        )
    