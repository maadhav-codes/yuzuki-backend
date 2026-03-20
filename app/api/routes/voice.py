from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.core.auth import get_current_user
from app.models.models import User
from app.schemas.schemas import VoiceConfigResponse, VoiceTTSRequest
from app.services.tts_service import tts_service

router = APIRouter(tags=["voice"])


@router.post("/voice/tts")
async def text_to_speech(
    tts: VoiceTTSRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        wav_bytes = tts_service.synthesize(
            text=tts.text,
            emotion=tts.emotion,
            speed=tts.speed,
            style_weight=tts.styleWeight,
            language=tts.language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"TTS unavailable: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"TTS synthesis failed: {exc}"
        ) from exc

    return Response(content=wav_bytes, media_type="audio/wav")


@router.get("/voice/config", response_model=VoiceConfigResponse)
async def voice_config(
    current_user: User = Depends(get_current_user),
):
    return VoiceConfigResponse(
        supportedLanguages=["en", "ja", "zh"], defaultVoice="sbv2"
    )
