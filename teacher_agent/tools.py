# Copyright 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Custom function tools for the book assistant agent."""

import os
from typing import Dict, Any
from google.genai import types
from google.cloud import storage
import requests
from io import BytesIO


def get_book_page(book_name: str, page_number: int) -> Dict[str, Any]:
    """
    Retrieves a specific page from a book stored in Google Cloud Storage.
    
    This tool allows the agent to access book page images stored in GCS.
    Each book is stored in a separate folder (e.g., math-1/, math-2/), 
    and pages are named as page_X.png where X is the page number.
    
    Args:
        book_name (str): The name of the book folder (e.g., "math-1", "math-2").
        page_number (int): The page number to retrieve (e.g., 5, 15, 100).
    
    Returns:
        dict: A dictionary containing:
            - status (str): "success" if the page is found, "error" otherwise
            - message (str): A descriptive message about the result
            - image (Part): The image as a Part object (only if status is "success")
            - book_name (str): The requested book name
            - page_number (int): The requested page number
    """
    # GCS configuration
    BUCKET_NAME = "bakaloria-ai-assistance-books"
    USE_GCS = True  # Set to False to use local files for development
    
    # Construct the blob path
    page_filename = f"page_{page_number}.png"
    blob_path = f"{book_name}/{page_filename}"
    
    try:
        if USE_GCS:
            # Fetch from Google Cloud Storage
            try:
                # Initialize the storage client
                client = storage.Client()
                bucket = client.bucket(BUCKET_NAME)
                blob = bucket.blob(blob_path)
                
                # Check if the blob exists
                if not blob.exists():
                    # Try to list available pages for this book
                    blobs = list(bucket.list_blobs(prefix=f"{book_name}/page_"))
                    available_pages = []
                    for b in blobs:
                        if b.name.endswith(".png"):
                            try:
                                page_num = int(b.name.split("page_")[1].replace(".png", ""))
                                available_pages.append(page_num)
                            except (IndexError, ValueError):
                                continue
                    
                    if not available_pages:
                        # Check if the book exists at all
                        book_blobs = list(bucket.list_blobs(prefix=f"{book_name}/", max_results=1))
                        if not book_blobs:
                            # List available books
                            prefixes = set()
                            for b in bucket.list_blobs():
                                if "/" in b.name:
                                    prefixes.add(b.name.split("/")[0])
                            available_books = sorted(prefixes)
                            return {
                                "status": "error",
                                "message": f"Book '{book_name}' not found. Available books: {', '.join(available_books)}",
                                "book_name": book_name,
                                "page_number": page_number
                            }
                    
                    available_pages.sort()
                    page_range = f"{min(available_pages)}-{max(available_pages)}" if available_pages else "none"
                    
                    return {
                        "status": "error",
                        "message": f"Page {page_number} not found in book '{book_name}'. Available pages: {page_range}",
                        "book_name": book_name,
                        "page_number": page_number
                    }
                
                # Download the image bytes
                image_bytes = blob.download_as_bytes()
                
            except Exception as gcs_error:
                # If GCS fails, try public URL as fallback
                public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_path}"
                response = requests.get(public_url)
                if response.status_code != 200:
                    raise Exception(f"Failed to fetch from GCS: {gcs_error}")
                image_bytes = response.content
        
        else:
            # Fallback to local files for development
            base_dir = os.path.dirname(os.path.abspath(__file__))
            books_dir = os.path.join(base_dir, "books")
            book_path = os.path.join(books_dir, book_name)
            page_path = os.path.join(book_path, page_filename)
            
            if not os.path.exists(page_path):
                return {
                    "status": "error",
                    "message": f"Page {page_number} not found in book '{book_name}' (local mode)",
                    "book_name": book_name,
                    "page_number": page_number
                }
            
            with open(page_path, 'rb') as image_file:
                image_bytes = image_file.read()
        
        # Create a Part object with the image data
        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type="image/png"
        )
        
        source = "GCS" if USE_GCS else "local"
        return {
            "status": "success",
            "message": f"Successfully retrieved page {page_number} from book '{book_name}' ({source})",
            "image": image_part,  # Return the Part object
            "book_name": book_name,
            "page_number": page_number
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error reading image file: {str(e)}",
            "book_name": book_name,
            "page_number": page_number
        }
