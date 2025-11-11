from pydantic_settings import BaseSettings, SettingsConfigDict


class TwilioSettings(BaseSettings):
    account_sid: str 
    auth_token: str 
    whatsapp_sender_number: str 
    phone_number: str

    model_config = SettingsConfigDict(
        env_file = ".env",
        env_prefix = "TWILIO_",
        extra = "ignore"
    )


settings = TwilioSettings()

