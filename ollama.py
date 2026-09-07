# Установи: pip install ollama
import ollama

def get_ai_analysis_ollama(prompt: str, contract_text: str) -> str:
    """Использует локальную модель через Ollama"""
    response = ollama.chat(
        model="llama3",  # или "mistral", "gemma:2b" (бесплатно)
        messages=[
            {"role": "system", "content": "Ты юрист. Анализируй договоры."},
            {"role": "user", "content": f"{prompt}\n\n{contract_text[:10000]}"}
        ]
    )
    return response['message']['content']
  
