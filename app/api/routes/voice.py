from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.models.models import User
from app.schemas.schemas import VoiceConfigResponse, VoiceTTSRequest, VoiceTTSResponse

router = APIRouter(tags=["voice"])


@router.post("/voice/tts", response_model=VoiceTTSResponse)
async def text_to_speech(
    tts: VoiceTTSRequest,
    current_user: User = Depends(get_current_user),
):
    return VoiceTTSResponse(
        success=True,
        audioUrl=None,
        note="Client-side TTS is currently used, so no audio URL is provided",
    )


@router.get("/voice/config", response_model=VoiceConfigResponse)
async def voice_config(
    current_user: User = Depends(get_current_user),
):
    return VoiceConfigResponse(supportedLanguages=["en-US"], defaultVoice="default")
