#!/usr/bin/env python3
"""
PDF to Images Converter
Converts each page of a PDF file to individual images.
Each image is named with the page number.

Usage:
    python pdf_to_images.py <pdf_file>

Example:
    python pdf_to_images.py 12-sci-math-1.pdf

Requirements:
    - pdf2image library: pip install pdf2image
    - poppler: brew install poppler (macOS)
"""

import sys
import os
from pathlib import Path

try:
    from pdf2image import convert_from_path
except ImportError:
    print("Error: pdf2image library is not installed.")
    print("Please install it using: pip install pdf2image")
    print("Also ensure poppler is installed: brew install poppler (macOS)")
    sys.exit(1)


def pdf_to_images(pdf_path, output_dir=None, image_format='png', dpi=200):
    """
    Convert PDF pages to images.
    
    Args:
        pdf_path: Path to the PDF file
        output_dir: Directory to save images (default: creates folder named after PDF)
        image_format: Image format ('png' or 'jpg')
        dpi: Resolution of output images (default: 200)
    """
    # Check if PDF file exists
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file '{pdf_path}' not found.")
        sys.exit(1)
    
    # Get PDF filename without extension
    pdf_name = Path(pdf_path).stem
    
    # Set output directory
    if output_dir is None:
        output_dir = f"{pdf_name}_images"
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Converting '{pdf_path}' to images...")
    print(f"Output directory: {output_dir}")
    
    try:
        # Convert PDF to images
        images = convert_from_path(pdf_path, dpi=dpi)
        
        print(f"Total pages: {len(images)}")
        
        # Save each page as an image
        for i, image in enumerate(images, start=1):
            image_filename = f"page_{i}.{image_format}"
            image_path = os.path.join(output_dir, image_filename)
            image.save(image_path, image_format.upper())
            print(f"Saved: {image_filename}")
        
        print(f"\nConversion complete! {len(images)} images saved to '{output_dir}'")
        
    except Exception as e:
        print(f"Error during conversion: {e}")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: python pdf_to_images.py <pdf_file>")
        print("Example: python pdf_to_images.py 12-sci-math-1.pdf")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    # Optional: Allow custom output directory as second argument
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    pdf_to_images(pdf_path, output_dir)


if __name__ == "__main__":
    main()
