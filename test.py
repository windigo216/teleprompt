import openai
import requests
from io import BytesIO
from PIL import Image
import os
from dotenv import load_dotenv

# Set your API key
load_dotenv(".env")
openai.api_key = os.getenv("OPENAI_API_KEY")


def generate_image(prompt, size="1024x1024", quality="standard"):
    try:
        response = openai.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
        )
        
        image_url = response.data[0].url
        return image_url
        
    except Exception as e:
        print(f"Error generating image: {e}")
        return None

def download_and_save_image(image_url, filename="generated_image.png"):
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        
        # Save the image
        with open(filename, 'wb') as file:
            file.write(response.content)
        
        print(f"Image saved as {filename}")
        return filename
        
    except Exception as e:
        print(f"Error downloading image: {e}")
        return None

# Complete example
def generate_and_save_image(prompt, filename="output.png"):
    image_url = generate_image(prompt)
    if image_url:
        download_and_save_image(image_url, filename)
        return filename
    return None

# Usage
generate_and_save_image("A futuristic city with flying cars", "future_city.png")