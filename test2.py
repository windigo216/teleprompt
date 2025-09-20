# This is for the inverse game mode. Input is image, output is text describing the image.
import openai
import base64
import os
from dotenv import load_dotenv

# Set your API key
load_dotenv(".env")
openai.api_key = os.getenv("OPENAI_API_KEY")

def encode_image(image_path):
    """Encode image to base64 for the API"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def describe_image(image_path, detail_level="high"):
    """
    Generate a text description of an image using GPT-4 Vision
    
    Parameters:
    - image_path: Path to the image file
    - detail_level: "low", "high", or "auto" (for the API)
    """
    try:
        # Encode the image
        base64_image = encode_image(image_path)
        
        # Call the OpenAI API
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": "Describe this image in detail. It is a very rough outlined line drawing. The user had a specific non-abstract non-random goal when drawing this iamge. If the user had more time to continue (or was better at drawing), what would this be? Describe objects, colors, composition, style, and any text present. Your description should be detailed enough that someone could use it to try to recreate a similar image with an AI image generator. However, it must be short enough that someone can read it within 5 seconds or less (keep it to 20-30 words)."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": detail_level
                            }
                        }
                    ]
                }
            ],
            max_tokens=500
        )
        
        description = response.choices[0].message.content
        return description
        
    except Exception as e:
        print(f"Error describing image: {e}")
        return None

def save_description(description, filename="image_description.txt"):
    """Save the description to a text file"""
    try:
        with open(filename, 'w') as file:
            file.write(description)
        print(f"Description saved as {filename}")
        return filename
    except Exception as e:
        print(f"Error saving description: {e}")
        return None

def describe_and_save_image(image_path, text_filename="image_description.txt"):
    """Complete function to describe an image and save the result"""
    description = describe_image(image_path)
    if description:
        save_description(description, text_filename)
        return description
    return None

# Usage example
if __name__ == "__main__":
    # Describe an image and save the text
    image_path = "scribbles.png"  # Replace with your image path
    description = describe_and_save_image(image_path, "description_of_future_city.txt")
    
    if description:
        print("Image Description:")
        print(description)
