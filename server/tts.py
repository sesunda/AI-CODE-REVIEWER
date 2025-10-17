"""
Text-to-Speech integration using ElevenLabs.
Provides audio generation for code review summaries and findings.
"""

import os
import asyncio
import base64
from typing import Optional, Dict, Any
from dataclasses import dataclass

try:
    from elevenlabs import generate, set_api_key, voices
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False


@dataclass
class AudioConfig:
    """Configuration for text-to-speech generation"""
    voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Default ElevenLabs voice
    model_id: str = "eleven_monolingual_v1"
    voice_settings: Dict[str, float] = None
    
    def __post_init__(self):
        if self.voice_settings is None:
            self.voice_settings = {
                "stability": 0.5,
                "similarity_boost": 0.5
            }


class TTSManager:
    """Text-to-Speech manager using ElevenLabs"""
    
    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self.enabled = ELEVENLABS_AVAILABLE and bool(self.api_key)
        
        if self.enabled:
            set_api_key(self.api_key)
    
    async def generate_audio(
        self, 
        text: str, 
        config: Optional[AudioConfig] = None
    ) -> Optional[bytes]:
        """Generate audio from text"""
        if not self.enabled:
            return None
        
        if not text.strip():
            return None
        
        config = config or AudioConfig()
        
        try:
            # Generate audio using ElevenLabs
            audio = await asyncio.to_thread(
                generate,
                text=text,
                voice=config.voice_id,
                model=config.model_id,
                voice_settings=config.voice_settings
            )
            return audio
        except Exception as e:
            print(f"TTS generation error: {e}")
            return None
    
    async def generate_review_audio(
        self, 
        review_summary: str,
        findings: list,
        config: Optional[AudioConfig] = None
    ) -> Optional[bytes]:
        """Generate audio for a complete code review"""
        if not self.enabled:
            return None
        
        # Create a comprehensive audio script
        script_parts = []
        
        # Add summary
        if review_summary:
            script_parts.append(f"Code review summary: {review_summary}")
        
        # Add findings
        if findings:
            script_parts.append("Issues found:")
            for i, finding in enumerate(findings[:3], 1):  # Limit to first 3 findings
                if isinstance(finding, dict):
                    agent = finding.get("agent", "unknown")
                    summary = finding.get("summary", "No summary")
                    script_parts.append(f"Issue {i} from {agent}: {summary}")
        
        # Join all parts
        full_script = ". ".join(script_parts)
        
        return await self.generate_audio(full_script, config)
    
    async def get_available_voices(self) -> list:
        """Get list of available voices"""
        if not self.enabled:
            return []
        
        try:
            voices_list = await asyncio.to_thread(voices)
            return [
                {
                    "voice_id": voice.voice_id,
                    "name": voice.name,
                    "category": voice.category
                }
                for voice in voices_list
            ]
        except Exception as e:
            print(f"Error fetching voices: {e}")
            return []
    
    def audio_to_base64(self, audio_bytes: bytes) -> str:
        """Convert audio bytes to base64 string for API responses"""
        return base64.b64encode(audio_bytes).decode('utf-8')


# Global TTS manager instance
tts_manager = TTSManager()
