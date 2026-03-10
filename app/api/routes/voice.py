from fastapi import APIRouter

from schemas import VoiceConfigResponse, VoiceTTSRequest, VoiceTTSResponse

router = APIRouter(tags=["voice"])


@router.post("/voice/tts", response_model=VoiceTTSResponse)
async def text_to_speech(tts: VoiceTTSRequest):
    return VoiceTTSResponse(
        success=True,
        audioUrl=None,
        note="Client-side TTS is currently used, so no audio URL is provided",
    )


@router.get("/voice/config", response_model=VoiceConfigResponse)
async def voice_config():
    return VoiceConfigResponse(supportedLanguages=["en-US"], defaultVoice="default")
