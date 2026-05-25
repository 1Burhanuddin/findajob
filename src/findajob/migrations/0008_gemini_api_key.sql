-- Add user_gemini_api_key column to onboarding_sessions (#870).
-- Optional Google AI API key for Gemini TTS podcast generation.
ALTER TABLE onboarding_sessions ADD COLUMN user_gemini_api_key TEXT DEFAULT NULL;
