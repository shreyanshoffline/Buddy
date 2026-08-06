import os
import requests
import pyttsx3

# Put your secret token here
HF_TOKEN = ""

API_URL = "https://huggingface.co"
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

engine = pyttsx3.init()
print("🦖 Hackky Buddy is online! Type 'exit' to quit.\n")

while True:
    user_input = input("You: ")
    if user_input.lower() == 'exit':
        break
        
    payload = {
        "inputs": f"<|system|>\nYou are Hackky Buddy, the smart dinosaur mascot for Hack Club. Keep responses under 2 sentences.<|user|>\n{user_input}<|assistant|>\n",
        "parameters": {"max_new_tokens": 80, "return_full_text": False}
    }
        
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        output = response.json()
        
        if isinstance(output, dict) and "error" in output:
            raise Exception(output["error"])
            
        # Fixes the 'list' object error instantly:
        if isinstance(output, list):
            reply = output[0]['generated_text'].strip()
        else:
            reply = output["choices"][0]["message"]["content"].strip()
            
        print(f"\nHackky Buddy: {reply}\n")
        engine.say(reply)
        engine.runAndWait()
        
    except Exception as e:
        print(f"\n⚠️ DEBUG ERROR: {e}\n")
