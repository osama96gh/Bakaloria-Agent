#!/usr/bin/env python3
"""
Script to create a GCS bucket and upload book images to Google Cloud Storage.
This will help reduce the deployment package size.
"""

import os
from google.cloud import storage
from pathlib import Path

# Set the project ID
PROJECT_ID = "bakaloria-ai-assistance"
BUCKET_NAME = "bakaloria-ai-assistance-books"
LOCATION = "us-central1"
LOCAL_BOOKS_PATH = "teacher_agent/books"

def create_bucket_if_not_exists(client, bucket_name, location):
    """Create a GCS bucket if it doesn't exist."""
    try:
        bucket = client.get_bucket(bucket_name)
        print(f"✅ Bucket {bucket_name} already exists")
        return bucket
    except:
        # Bucket doesn't exist, create it
        bucket = client.bucket(bucket_name)
        bucket.location = location
        bucket = client.create_bucket(bucket)
        print(f"✅ Created bucket {bucket_name} in {location}")
        return bucket

def upload_directory_to_gcs(client, bucket_name, local_directory):
    """Upload all files from a local directory to GCS, maintaining folder structure."""
    bucket = client.bucket(bucket_name)
    
    # Count total files for progress tracking
    total_files = sum(1 for _ in Path(local_directory).rglob("*.png"))
    uploaded_count = 0
    
    print(f"📤 Uploading {total_files} PNG files to GCS...")
    
    for local_file in Path(local_directory).rglob("*.png"):
        # Create the blob path maintaining the folder structure
        relative_path = local_file.relative_to(local_directory)
        blob_name = str(relative_path)
        
        # Upload the file
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(str(local_file))
        
        uploaded_count += 1
        if uploaded_count % 10 == 0:  # Progress update every 10 files
            print(f"   Uploaded {uploaded_count}/{total_files} files...")
    
    print(f"✅ Successfully uploaded {uploaded_count} files to gs://{bucket_name}/")
    return uploaded_count

def make_bucket_public_read(client, bucket_name):
    """Make the bucket publicly readable."""
    bucket = client.bucket(bucket_name)
    policy = bucket.get_iam_policy(requested_policy_version=3)
    
    # Add public read access
    policy.bindings.append({
        "role": "roles/storage.objectViewer",
        "members": ["allUsers"]
    })
    
    bucket.set_iam_policy(policy)
    print(f"✅ Bucket {bucket_name} is now publicly readable")

def main():
    # Set the environment variable for authentication
    os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
    
    print(f"🚀 Starting GCS upload process...")
    print(f"   Project: {PROJECT_ID}")
    print(f"   Bucket: {BUCKET_NAME}")
    print(f"   Location: {LOCATION}")
    print()
    
    try:
        # Initialize the client
        client = storage.Client(project=PROJECT_ID)
        
        # Create bucket if it doesn't exist
        bucket = create_bucket_if_not_exists(client, BUCKET_NAME, LOCATION)
        
        # Upload all book images
        if os.path.exists(LOCAL_BOOKS_PATH):
            file_count = upload_directory_to_gcs(client, BUCKET_NAME, LOCAL_BOOKS_PATH)
            
            # Make bucket publicly readable (optional - remove if you want private access)
            # make_bucket_public_read(client, BUCKET_NAME)
            
            print()
            print("🎉 Upload complete!")
            print(f"   Your book images are now available at:")
            print(f"   gs://{BUCKET_NAME}/")
            print()
            print("📝 Next steps:")
            print("   1. Update your agent code to fetch images from GCS")
            print("   2. Test the deployment with 'make backend'")
        else:
            print(f"❌ Error: Directory {LOCAL_BOOKS_PATH} not found")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure you have authenticated with Google Cloud:")
        print("   gcloud auth application-default login")
        print("2. Ensure the Cloud Storage API is enabled:")
        print("   gcloud services enable storage.googleapis.com")

if __name__ == "__main__":
    main()
