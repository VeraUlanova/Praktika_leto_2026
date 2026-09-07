# Альтернатива через OpenAI (нужен ключ)
import openai

openai.api_key = "YOUR_OPENAI_KEY"  # Бесплатные $5 при регистрации

def get_ai_analysis_openai(prompt: str, contract_text: str) -> str:
    """Использует ChatGPT вместо Gemini"""
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",  # Самая дешевая модель
        messages=[
            {"role": "system", "content": "Ты опытный юрист. Анализируй договоры."},
            {"role": "user", "content": f"{prompt}\n\nТекст: {contract_text[:10000]}"}
        ],
        temperature=0.3,
        max_tokens=1500
    )
    return response.choices[0].message.content
  
