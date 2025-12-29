from typing import Annotated, Union

from fastapi import APIRouter, Depends, Body, Request, HTTPException
from fastapi.responses import StreamingResponse

from api.auth import api_key_auth
#from api.models.ociodsc import OCIOdscModel
from openai.types.audio.transcription import Transcription
from openai.types.audio.transcription_create_params import TranscriptionCreateParamsBase

# Import OCI Speech SDK
from oci_ai_speech_realtime import RealtimeSpeechClient, RealtimeSpeechClientListener
from oci.ai_speech.models import RealtimeParameters
from oci.config import from_file
from oci.auth.signers.security_token_signer import SecurityTokenSigner
import oci.signer

import asyncio
import io
import logging
from fastapi import UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Optional

from config import OCI_COMPARTMENT, OCI_REGION

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/audio",
    dependencies=[Depends(api_key_auth)]
)

speech_config = from_file()

class TranscriptionListener(RealtimeSpeechClientListener):
    """Listener for collecting transcription results from OCI Speech service."""

    def __init__(self):
        self.final_transcription = ""
        self.partial_transcriptions = []
        self.error_message = None
        self.connected = False
        self.done = False
        self.final_chunk = False

    def on_result(self, result):
        """Handle transcription results."""
        try:
            logger.debug(f"Received result: {result}")
            transcriptions = result.get("transcriptions", [])
            if transcriptions:
                transcription_text = transcriptions[0].get("transcription", "")
                is_final = transcriptions[0].get("isFinal", False)

                if is_final:
                    self.final_transcription += transcription_text + " "
                    if self.final_chunk:
                        self.done = True
                    logger.info(f"Transcription: {transcription_text}")
                else:
                    self.partial_transcriptions.append(transcription_text)
                    logger.debug(f"Partial transcription: {transcription_text}")
        except Exception as e:
            logger.error(f"Error processing result: {e}")
            self.error_message = str(e)
            self.done = True

    def on_error(self, error):
        """Handle errors."""
        #logger.error(f"Transcription error: {error}")
        self.error_message = str(error)
        self.done = True

    def on_connect(self):
        """Handle connection established."""
        logger.info("Connected to OCI Speech service")
        self.connected = True

    def on_connect_message(self, connectmessage):
        """Handle connect message."""
        logger.info("Connected to OCI Speech service")
        self.connected = True

    def on_ack_message(self, ackmessage):
        """Handle acknowledgment message."""
        pass

    def on_network_event(self, message):
        """Handle network events."""
        pass

    def on_close(self, error_code, error_message):
        """Handle connection close."""
        #logger.info(f"Connection closed: {error_code} - {error_message}")
        self.done = True


def get_authenticator():
    """Get OCI authenticator based on available credentials."""
    try:
        # Try security token first (common in cloud environments)
        config = from_file("~/.oci/config", "DEFAULT")
        with open(config["security_token_file"], "r") as f:
            token = f.read().strip()

        private_key = oci.signer.load_private_key_from_file(config["key_file"])
        return SecurityTokenSigner(token=token, private_key=private_key)
    except Exception:
        try:
            # Fall back to config file auth
            config = from_file("~/.oci/config", "DEFAULT")
            return oci.signer.Signer(
                tenancy=config["tenancy"],
                user=config["user"],
                fingerprint=config["fingerprint"],
                private_key_file_location=config.get("key_file"),
                pass_phrase=config.get("pass_phrase"),
                private_key_content=config.get("key_content"),
            )
        except Exception as f:
            #logger.error(f"Config file auth failed: {e}")
            raise RuntimeError(f"Unable to authenticate with OCI. Please check your credentials. {f}") from f


def get_realtime_parameters(language: str = "en-US", model_type: str = "ORACLE") -> RealtimeParameters:
    """Create RealtimeParameters with default settings."""
    params = RealtimeParameters()
    params.language_code = language
    params.model_domain = RealtimeParameters.MODEL_DOMAIN_GENERIC
    params.model_type = model_type
    #params.partial_silence_threshold_in_ms = 0
    #params.final_silence_threshold_in_ms = 2000
    params.encoding = "audio/raw;rate=16000"
    #params.should_ignore_invalid_customizations = False
    #params.stabilize_partial_results = RealtimeParameters.STABILIZE_PARTIAL_RESULTS_NONE
    params.punctuation = RealtimeParameters.PUNCTUATION_NONE
    return params


async def transcribe_audio_file(
    audio_data: bytes,
    language: str = "en-US",
    model_type: str = "ORACLE",
    compartment_id: Optional[str] = None,
    region: str = "us-ashburn-1"
) -> str:
    """
    Transcribe audio file using OCI Speech Realtime service.

    Args:
        audio_data: Raw audio bytes
        language: Language code (e.g., "en-US")
        compartment_id: OCI compartment ID
        region: OCI region

    Returns:
        Transcribed text
    """
    if not compartment_id:
        raise ValueError("compartment_id is required")

    # Create listener
    listener = TranscriptionListener()

    # Get authentication
    signer = get_authenticator()

    # Create parameters
    params = get_realtime_parameters(language, model_type)

    # Create client
    service_endpoint = f"wss://realtime.aiservice.{region}.oci.oraclecloud.com"
    client = RealtimeSpeechClient(
        config=speech_config,  # Config handled by signer
        realtime_speech_parameters=params,
        listener=listener,
        service_endpoint=service_endpoint,
        signer=signer,
        compartment_id=compartment_id,
    )

    try:
        # Connect to service
        connect_task = asyncio.create_task(client.connect())

        # Wait for connection
        while not listener.connected and not client.close_flag:
            await asyncio.sleep(0.1)  # Brief pause to establish connection

        # Stream audio data in chunks
        #chunk_size = 16000 * 2 * 5.500  # 96ms chunks at 16kHz, 16-bit
        chunk_size = int(65536) # Use 64KB chunks

        audio_stream = io.BytesIO(audio_data)
        while not listener.done and not client.close_flag:
            chunk = audio_stream.read(chunk_size)
            if not chunk:
                break

            await client.send_data(chunk)
            await asyncio.sleep(0.100)  # Small delay between chunks

        # Request final result
        #listener.final_chunk = True

        await client.request_final_result()
        
        # Wait for completion
        timeout = 30  # 30 second timeout
        for _ in range(timeout * 10):
            if listener.done:
                break
            await asyncio.sleep(0.1)

        # Close client
        client.close()

        # Wait for connect task if still running
        try:
            await asyncio.wait_for(connect_task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        if listener.error_message:
            raise RuntimeError(f"Transcription failed: {listener.error_message}")

        return listener.final_transcription or " ".join(listener.partial_transcriptions)

    except Exception as e:
        client.close()
        raise e


@router.post(
    "/transcriptions", 
    response_model=Union[Transcription], 
    response_model_exclude_unset=True
    )
async def transcriptions(
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),  # OpenAI compatible parameter
    language: Optional[str] = Form(None),
    response_format: str = Form("json"),
    temperature: Optional[float] = Form(None),
    #compartment_id: str = Form(...),
    #region: str = Form("us-ashburn-1")
):
    """
    OpenAI-compatible audio transcription endpoint.

    Args:
        file: Audio file to transcribe
        model: Model to use (ignored, always uses OCI)
        language: Language code (optional)
        response_format: Response format (json/text/srt/verbose_json)
        temperature: Temperature (ignored)
        compartment_id: OCI compartment ID (required)
        region: OCI region (default: us-ashburn-1)
    """

    try:
        
        if not file:
            raise HTTPException(status_code=400, detail="Audio file is required")

        # Read audio data
        audio_data = await file.read()

        if len(audio_data) == 0:
            raise HTTPException(status_code=400, detail="Empty file provided")

        # Default language if not provided
        if not language:
            language = "en-US"

        # Transcribe audio
        transcription = await transcribe_audio_file(
            audio_data=audio_data,
            language=language,
            model_type=model,
            compartment_id=OCI_COMPARTMENT,
            region=OCI_REGION
        )

        # Format response based on response_format
        if response_format == "json":
            return JSONResponse({
                "text": transcription
            })
        elif response_format == "text":
            return JSONResponse(content=transcription, media_type="text/plain")
        elif response_format == "srt":
            # Simple SRT format (placeholder - would need proper timing)
            srt_content = "1\n00:00:00,000 --> 00:00:10,000\n" + transcription + "\n"
            return JSONResponse(content=srt_content, media_type="text/plain")
        elif response_format == "verbose_json":
            return JSONResponse({
                "task": "transcribe",
                "language": language,
                "duration": None,  # Would need audio duration calculation
                "text": transcription,
                "segments": []  # Would need segment-level results
            })
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported response format: {response_format}")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        #logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e
