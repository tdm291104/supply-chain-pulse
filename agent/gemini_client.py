"""Thin wrapper over google-generativeai.

Isolated behind this module so analysis/chat code never touches the SDK
directly — makes both unit testing (via monkeypatching _build_model) and
a future model swap straightforward.
"""
import json

import google.generativeai as genai


def _build_model(model_name: str, system_instruction: str):
    return genai.GenerativeModel(model_name=model_name, system_instruction=system_instruction)


class GeminiClient:
    def __init__(self, api_key: str, model_name: str):
        genai.configure(api_key=api_key)
        self._model_name = model_name

    def generate_json(self, *, system_instruction: str, prompt: str, response_schema: dict) -> dict:
        model = _build_model(self._model_name, system_instruction)
        response = model.generate_content(
            prompt,
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": response_schema,
            },
            request_options={"timeout": 30, "retry": None},
        )
        return json.loads(response.text)

    def generate_text(self, *, system_instruction: str, prompt: str) -> str:
        model = _build_model(self._model_name, system_instruction)
        response = model.generate_content(
            prompt,
            request_options={"timeout": 30, "retry": None},
        )
        return response.text
