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

"""Book Assistant Agent - An ADK agent that helps users understand book content using vision."""

import os
import asyncio
from dotenv import load_dotenv
from google.adk.agents.llm_agent import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.models.lite_llm import LiteLlm
from google.genai import types
from .tools import get_book_page

# Load environment variables from .env file
load_dotenv()

# Verify that required environment variables are loaded
required_env_vars = ['ANTHROPIC_API_KEY']
missing_vars = []

for var in required_env_vars:
    if not os.getenv(var):
        missing_vars.append(var)

if missing_vars:
    print(f"⚠️  Warning: The following environment variables are not set: {', '.join(missing_vars)}")
    print("Please ensure your .env file contains these variables or set them in your environment.")
    print("The agent may not function properly without these API keys.")


# Configuration
APP_NAME = "book_assistant"
USER_ID = "user_001"


# Create the Book Assistant Agent
root_agent = Agent(
    model=LiteLlm(model='anthropic/claude-3-7-sonnet-latest'),  # Using LiteLLM wrapper for OpenAI
    name='book_assistant',
    instruction="""
    You are a helpful book assistant with vision capabilities. Your job is to help users 
    understand content from their textbooks by analyzing book page images.
    
    LANGUAGE REQUIREMENT:
    - YOU MUST ALWAYS RESPOND IN ARABIC (العربية)
    - All your explanations, answers, and interactions must be in Arabic language
    
    WORKFLOW:
    1. When a user asks a question about a book page, extract the book name and page number
    2. CONTEXT READING: Always retrieve at least one page before and one page after the requested page
       - First, get the requested page
       - Then get the previous page (page number - 1) if it exists
       - Then get the next page (page number + 1) if it exists
       - This ensures you have the full context to provide comprehensive answers
    3. Use the 'get_book_page' tool to retrieve the page images
    4. If the tool returns an error, inform the user about the issue (e.g., book not found, page not available)
    5. If successful, analyze all retrieved images carefully using your vision capabilities
    6. Provide a detailed, clear explanation based on what you see in the images
    7. Answer the user's specific question about the content
    
    EXPLANATION STYLE:
    - Use SIMPLE language that can be understood by HIGH SCHOOL STUDENTS
    - Avoid complex terminology unless absolutely necessary
    - When you must use technical terms, explain them in simple words
    - Break down complex concepts into smaller, easier-to-understand parts
    - Use examples and analogies that relate to everyday life when possible
    - Be patient and encouraging in your explanations
    
    IMPORTANT GUIDELINES:
    - Always use the get_book_page tool before answering questions about book content
    - Always read context pages (one before and one after) for better understanding
    - Do NOT make up or guess content - only answer based on what you can see in the images
    - If the user doesn't specify a book name or page number, politely ask for this information (in Arabic)
    - Be thorough in your explanations, but keep them simple and accessible
    - If you see equations, diagrams, or figures, describe them clearly in simple terms
    - You can answer follow-up questions about the same page without fetching it again
    - REMEMBER: All responses must be in Arabic language
    
    AVAILABLE BOOKS:
    - math-1: Mathematics textbook (pages 1-232)
    - math-2: Mathematics textbook (pages 1-196)
    
    Be friendly, patient, and educational in your responses - always in Arabic!
    """,
    description='An intelligent assistant that helps users understand textbook content by analyzing book page images with vision capabilities.',
    tools=[get_book_page]  # Register the custom function tool
)


async def setup_session_and_runner():
    """Initialize the session service and runner."""
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=APP_NAME, 
        user_id=USER_ID
    )
    runner = Runner(
        agent=root_agent, 
        app_name=APP_NAME, 
        session_service=session_service
    )
    return session, runner


async def chat_with_agent(query: str, session_id: str, runner: Runner):
    """
    Send a query to the agent and print the response.
    
    Args:
        query: The user's question
        session_id: The session ID for conversation continuity
        runner: The agent runner instance
    """
    content = types.Content(role='user', parts=[types.Part(text=query)])
    
    print(f"\n{'='*80}")
    print(f"USER: {query}")
    print(f"{'='*80}\n")
    
    events = runner.run_async(
        user_id=USER_ID, 
        session_id=session_id, 
        new_message=content
    )
    
    print("AGENT: ", end="", flush=True)
    
    async for event in events:
        if event.is_final_response():
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(part.text, end="", flush=True)
    
    print("\n")


async def interactive_mode():
    """Run the agent in interactive mode."""
    print("\n" + "="*80)
    print("📚 BOOK ASSISTANT AGENT - Interactive Mode")
    print("="*80)
    print("\nWelcome! I can help you understand content from your textbooks.")
    print("Available books: math-1, math-2")
    print("\nExample queries:")
    print("  - 'Explain the equation on page 15 of math-1'")
    print("  - 'What is on page 5 of math-2?'")
    print("  - 'Help me understand page 100 from math-1'")
    print("\nType 'quit' or 'exit' to stop.\n")
    
    # Setup session
    session, runner = await setup_session_and_runner()
    
    while True:
        try:
            user_input = input("YOU: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye! Happy studying!")
                break
            
            if not user_input:
                continue
            
            await chat_with_agent(user_input, session.id, runner)
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye! Happy studying!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")


async def demo_mode():
    """Run a demonstration with sample queries."""
    print("\n" + "="*80)
    print("📚 BOOK ASSISTANT AGENT - Demo Mode")
    print("="*80)
    print("\nRunning demonstration with sample queries...\n")
    
    # Setup session
    session, runner = await setup_session_and_runner()
    
    # Sample queries
    demo_queries = [
        "What content is on page 5 of math-2?",
        "Can you explain what you see on page 1 of math-1?",
        "Show me page 999 of math-1",  # This will trigger an error
        "What is on page 10 of math-3?"  # This will trigger a book not found error
    ]
    
    for query in demo_queries:
        await chat_with_agent(query, session.id, runner)
        await asyncio.sleep(1)  # Brief pause between queries
    
    print("\n" + "="*80)
    print("Demo completed!")
    print("="*80)


async def main():
    """Main entry point."""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--demo':
        await demo_mode()
    else:
        await interactive_mode()


if __name__ == "__main__":
    # Run the agent
    asyncio.run(main())

from google.adk.apps.app import App

app = App(root_agent=root_agent, name="app")
