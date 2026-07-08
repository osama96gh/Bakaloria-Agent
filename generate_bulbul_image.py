#!/usr/bin/env python3
"""Generate a profile picture for Bulbul using Google Gemini API."""

import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# Configure the API
api_key = os.getenv('GEMINI_API_KEY')
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

client = genai.Client(api_key=api_key)

# Lower-cost Gemini image generation model
IMAGE_MODEL = os.getenv("BULBUL_IMAGE_MODEL", "gemini-3.1-flash-lite-image")

# Bulbul profile picture prompt
BULBUL_PROMPT = """
3D rendered Pixar-style Bulbul songbird character with a hilarious mischievous expression.
The bird has one eyebrow raised high with a cheeky smirk, like it just told a clever joke.
Big expressive eyes with a playful sparkle, looking slightly to the side like sharing a secret.
Wearing crooked round glasses sliding down its beak, and a cozy orange hoodie.
Messy spiky black crest on head like bedhead hair, adding to the goofy charm.
One wing doing a casual finger-gun gesture, the other wing holding a coffee mug that says "Math is hard".
Soft brown and cream feathers, fluffy and slightly ruffled.
Expression says: "I know this stuff is tough, but trust me, we got this!"
Warm studio lighting, soft orange gradient background.
Pixar/Disney animation quality, comedic character design.
The vibe is: smart class clown who actually helps you pass the exam.
"""

# Bulbul banner/description image prompt
BULBUL_BANNER_PROMPT = """
3D rendered Pixar-style wide banner for an educational app.
The same funny Bulbul songbird character: messy spiky black crest like bedhead, crooked round glasses sliding down beak, orange hoodie.
The bird is standing on a messy desk covered with scattered papers, coffee cups, and textbooks.
Mischievous cheeky expression, one eyebrow raised, holding a "Math is hard" coffee mug.
One wing pointing at a glowing holographic chalkboard with messy equations and doodles.
Around: floating books, crumpled paper balls, a glowing lightbulb above head (idea moment), calculator, pencils.
Cozy bedroom/study room with warm lighting, posters on wall, slightly chaotic but inviting.
The vibe: "yeah studying is messy, but we'll figure it out together".
Wide landscape composition (16:9 aspect ratio).
Pixar/Disney animation quality, comedic and relatable atmosphere.
No readable text except on the mug.
"""


def generate_bulbul_image(output_path: str = "bulbul_profile.png"):
    """Generate and save the Bulbul profile picture."""
    print(f"Generating Bulbul profile picture using {IMAGE_MODEL}...")

    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=BULBUL_PROMPT,
        config=types.GenerateContentConfig(
            response_modalities=['IMAGE', 'TEXT'],
        )
    )

    # Process the response
    for part in response.candidates[0].content.parts:
        if part.text is not None:
            print(f"Model response: {part.text}")
        elif part.inline_data is not None:
            # Save the image
            image_data = part.inline_data.data
            with open(output_path, 'wb') as f:
                f.write(image_data)
            print(f"Image saved to: {output_path}")
            return output_path

    print("No image was generated in the response")
    return None


def generate_bulbul_banner(output_path: str = "bulbul_banner.png"):
    """Generate and save the Bulbul banner/description image."""
    print(f"Generating Bulbul banner image using {IMAGE_MODEL}...")

    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=BULBUL_BANNER_PROMPT,
        config=types.GenerateContentConfig(
            response_modalities=['IMAGE', 'TEXT'],
        )
    )

    # Process the response
    for part in response.candidates[0].content.parts:
        if part.text is not None:
            print(f"Model response: {part.text}")
        elif part.inline_data is not None:
            # Save the image
            image_data = part.inline_data.data
            with open(output_path, 'wb') as f:
                f.write(image_data)
            print(f"Image saved to: {output_path}")
            return output_path

    print("No image was generated in the response")
    return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--banner":
        # Generate banner only
        output_file = generate_bulbul_banner()
        if output_file:
            print(f"\nSuccess! Banner saved to: {output_file}")
            print("\nTo set as Telegram description photo:")
            print("  1. Go to @BotFather → /setdescriptionpic")
            print(f"  2. Send the image: {output_file}")
    elif len(sys.argv) > 1 and sys.argv[1] == "--all":
        # Generate both images
        profile = generate_bulbul_image()
        banner = generate_bulbul_banner()
        print("\n" + "=" * 50)
        print("Generated images:")
        if profile:
            print(f"  Profile: {profile}")
        if banner:
            print(f"  Banner:  {banner}")
    else:
        # Default: generate profile picture
        output_file = generate_bulbul_image()
        if output_file:
            print(f"\nSuccess! Profile picture saved to: {output_file}")
            print("\nTo set as Telegram bot photo:")
            print("  1. Go to @BotFather → /setuserpic")
            print(f"  2. Send the image: {output_file}")
            print("\nTo generate banner: python generate_bulbul_image.py --banner")
