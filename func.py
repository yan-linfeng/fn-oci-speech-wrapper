
import io
import os
import oci
import time
import json
import datetime
from fdk import response

COMPARTMENT_ID = os.getenv("COMPARTMENT_ID")
OUTPUT_BUCKET = "bucket-audio-clips"
JOB_PREFIX = "STT"
LANGUAGE_CODE = "ja"

def handler(ctx, data: io.BytesIO=None):
    return speechToText(ctx,data)

def getSpeechClient():
    # config = oci.config.from_file(profile_name="DEFAULT")
    # ai_client = oci.ai_speech.AIServiceSpeechClient(config)
    signer = oci.auth.signers.get_resource_principals_signer()
    ai_client = oci.ai_speech.AIServiceSpeechClient(config={}, signer=signer)
    return ai_client

def get_object(bucketName, objectName):
    # config = oci.config.from_file(profile_name="DEFAULT")
    # client = oci.object_storage.ObjectStorageClient(config)
    signer = oci.auth.signers.get_resource_principals_signer()
    client = oci.object_storage.ObjectStorageClient(config={}, signer=signer)
    print("INFO: object_storage_client initilized")
    namespace = client.get_namespace().data
    try:
        print("Searching for bucket and object", flush=True)
        object = client.get_object(namespace, bucketName, objectName)
        print("found object", flush=True)
        if object.status == 200:
            print("Success: The object " + objectName + " was retrieved with the content: " + object.data.text, flush=True)
            message = object.data.text
        else:
            message = "Failed: The object " + objectName + " could not be retrieved."
    except Exception as e:
        message = "Failed: " + str(e.message)
    return { "content": message }

def get_namespace():
    signer = oci.auth.signers.get_resource_principals_signer()
    client = oci.object_storage.ObjectStorageClient(config={}, signer=signer)
    print("INFO: object_storage_client initilized")
    return client.get_namespace().data

def get_formatted_current_time():
    now = datetime.datetime.now()
    return now.strftime("%Y_%m_%d_%H%M_%S_%f")[:-3]

def speechToText(ctx, data: io.BytesIO=None):
    try:
        body = json.loads(data.getvalue())
        
        file_name = body["file_name"]
        bucket = body["bucket"]
        print("INFO: file_name parsed as {}, bucket parsed as {}".format(file_name,bucket), flush=True)
        
        ai_client = getSpeechClient()
        print("INFO: ai_client initilized")
        
        formatted_time = get_formatted_current_time()
        display_name = f"stt-job-{formatted_time}"
        description = f"stt-job-{formatted_time}"
        namespace = ai_client.get_namespace().data
        file_names = [file_name]
        
        MODEL_DETAILS = oci.ai_speech.models.TranscriptionModelDetails(model_type="WHISPER_MEDIUM", domain="GENERIC",  language_code=LANGUAGE_CODE,
            transcription_settings=oci.ai_speech.models.TranscriptionSettings(
                diarization=oci.ai_speech.models.Diarization(
                    is_diarization_enabled=False         
                )
            )
        )
        
        INPUT_LOCATION = oci.ai_speech.models.ObjectListInlineInputLocation(
            location_type="OBJECT_LIST_INLINE_INPUT_LOCATION", object_locations=[oci.ai_speech.models.ObjectLocation(namespace_name=namespace, bucket_name=bucket, object_names=file_names)])
        
        OUTPUT_LOCATION = oci.ai_speech.models.OutputLocation(namespace_name=namespace, bucket_name=bucket,
                                                             prefix=JOB_PREFIX)
        
        transcription_job_details = oci.ai_speech.models.CreateTranscriptionJobDetails(display_name=display_name,
                                                                               compartment_id=COMPARTMENT_ID,
                                                                               description=description,
                                                                               model_details=MODEL_DETAILS,
                                                                               input_location=INPUT_LOCATION,
                                                                               output_location=OUTPUT_LOCATION)

        transcription_job = None
        try:
            transcription_job = ai_client.create_transcription_job(create_transcription_job_details=transcription_job_details)
        except Exception as e:
            print(e)
        else:
            print(transcription_job.data)

        print("***GET TRANSCRIPTION JOB WITH ID***")
        try:
            if transcription_job.data:
                transcription_tasks = ai_client.list_transcription_tasks(transcription_job.data.id)
        except Exception as e:
            print(e)

        while transcription_tasks.status == 200 and len(transcription_tasks.data.items) == 0 :
            time.sleep(1)
            transcription_tasks = ai_client.list_transcription_tasks(transcription_job.data.id)
            
        while transcription_tasks.data.items[0].lifecycle_state == "IN_PROGRESS":
            time.sleep(1)
            transcription_tasks = ai_client.list_transcription_tasks(transcription_job.data.id)
            
        task = transcription_tasks.data.items[0]
        print(task.lifecycle_state)

        output_location = transcription_job.data.output_location.prefix + namespace + "_" + bucket + "_" + file_name + ".json"
        response_message = get_object(bucketName=bucket, objectName=output_location)
    except Exception as error:
        print(error)
        raise Exception(error)
    return response.Response(
        ctx,
        response_data=json.dumps(response_message),
        headers={"Content-Type": "application/json"}
    )
    

# ai_client = getSpeechClient()

# formatted_time = get_formatted_current_time()
# file_name = "audio-record-clip01.m4a";
# DISPLAY_NAME = f"stt-job-{formatted_time}"
# COMPARTMENT_ID = "ocid1.compartment.oc1..aaaaaaaahkek3btaogl6rgvp7fxciixdyjcejfybhf4k75ufuav3gxumahtq"
# DESCRIPTION = f"stt-job-{formatted_time}"
# NAMESPACE = "sehubjapacprod"
# BUCKET = "bucket-audio-clips"
# JOB_PREFIX = "STT"
# LANGUAGE_CODE = "ja"
# FILE_NAMES = [file_name]

# MODEL_DETAILS = oci.ai_speech.models.TranscriptionModelDetails(model_type="WHISPER_MEDIUM", domain="GENERIC",  language_code=LANGUAGE_CODE,
# transcription_settings=oci.ai_speech.models.TranscriptionSettings(
#     diarization=oci.ai_speech.models.Diarization(
#         is_diarization_enabled=False         
#     )
# )
# )
# SAMPLE_OBJECT_LOCATION = oci.ai_speech.models.ObjectLocation(namespace_name=NAMESPACE, bucket_name=BUCKET,
# object_names=FILE_NAMES)
# SAMPLE_INPUT_LOCATION = oci.ai_speech.models.ObjectListInlineInputLocation(
#     location_type="OBJECT_LIST_INLINE_INPUT_LOCATION", object_locations=[SAMPLE_OBJECT_LOCATION])
# SAMPLE_OUTPUT_LOCATION = oci.ai_speech.models.OutputLocation(namespace_name=NAMESPACE, bucket_name=BUCKET,
#                                                              prefix=JOB_PREFIX)

# transcription_job_details = oci.ai_speech.models.CreateTranscriptionJobDetails(display_name=DISPLAY_NAME,
#                                                                                compartment_id=COMPARTMENT_ID,
#                                                                                description=DESCRIPTION,
#                                                                                model_details=MODEL_DETAILS,
#                                                                                input_location=SAMPLE_INPUT_LOCATION,
#                                                                                output_location=SAMPLE_OUTPUT_LOCATION)

# transcription_job = None
# try:
#     transcription_job = ai_client.create_transcription_job(create_transcription_job_details=transcription_job_details)
# except Exception as e:
#     print(e)
# else:
#     print(transcription_job.data)

# print("***GET TRANSCRIPTION JOB WITH ID***")
# try:
#     if transcription_job.data:
#         transcription_tasks = ai_client.list_transcription_tasks(transcription_job.data.id)
# except Exception as e:
#     print(e)

# while transcription_tasks.status == 200 and len(transcription_tasks.data.items) == 0 :
#     time.sleep(1)
#     transcription_tasks = ai_client.list_transcription_tasks(transcription_job.data.id)
    
# while transcription_tasks.data.items[0].lifecycle_state == "IN_PROGRESS":
#     time.sleep(1)
#     transcription_tasks = ai_client.list_transcription_tasks(transcription_job.data.id)
    
# task = transcription_tasks.data.items[0]
# print(task.lifecycle_state)

# output_location = transcription_job.data.output_location.prefix + NAMESPACE + "_" + BUCKET + "_" + file_name + ".json"
# response_message = get_object(bucketName=BUCKET, objectName=output_location)
