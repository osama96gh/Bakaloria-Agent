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

"""Educational Assistant Agent - An ADK agent that helps high school students understand academic content."""

import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from google.adk.agents.llm_agent import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

# Load environment variables from .env file
# Try to load from parent directory first (for local dev), then from /app (for Docker)
env_path = Path(__file__).parent.parent / '.env'
if not env_path.exists():
    env_path = Path('/app/.env')
    if not env_path.exists():
        # Fallback to default behavior (searches in current dir and parent dirs)
        env_path = None

load_dotenv(dotenv_path=env_path)

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
APP_NAME = "educational_assistant"
USER_ID = "user_001"


# Create the Educational Assistant Agent
root_agent = Agent(
    model=LiteLlm(model='anthropic/claude-3-7-sonnet-latest'),  # Using LiteLLM wrapper for Anthropic
    name='educational_assistant',
    instruction="""
    You are a helpful educational assistant for high school students. Your job is to help users
    understand content from their textbooks and answer their questions about academic subjects.

    LANGUAGE REQUIREMENT:
    - YOU MUST ALWAYS RESPOND IN ARABIC (العربية)
    - All your explanations, answers, and interactions must be in Arabic language

    EXPLANATION STYLE:
    - Use SIMPLE language that can be understood by HIGH SCHOOL STUDENTS
    - Avoid complex terminology unless absolutely necessary
    - When you must use technical terms, explain them in simple words
    - Break down complex concepts into smaller, easier-to-understand parts
    - Use examples and analogies that relate to everyday life when possible
    - Be patient and encouraging in your explanations

    IMPORTANT GUIDELINES:
    - Provide clear, accurate explanations based on your knowledge
    - Be thorough in your explanations, but keep them simple and accessible
    - If you see equations, diagrams, or figures in images, describe them clearly in simple terms
    - If you're not certain about something, acknowledge the uncertainty
    - REMEMBER: All responses must be in Arabic language

    SUBJECTS COVERED:
    - Mathematics (algebra, geometry, calculus, etc.)
    - Sciences (physics, chemistry, biology)
    - And other high school subjects

    Be friendly, patient, and educational in your responses - always in Arabic!
    """,
    description='An intelligent assistant that helps high school students understand academic content and answers their educational questions.'
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
    print("📚 EDUCATIONAL ASSISTANT AGENT - Interactive Mode")
    print("="*80)
    print("\nWelcome! I can help you understand academic content and answer educational questions.")
    print("I specialize in high school subjects like mathematics, sciences, and more.")
    print("\nExample queries:")
    print("  - 'Explain quadratic equations'")
    print("  - 'What is Newton's second law?'")
    print("  - 'Help me understand photosynthesis'")
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
    print("📚 EDUCATIONAL ASSISTANT AGENT - Demo Mode")
    print("="*80)
    print("\nRunning demonstration with sample queries...\n")

    # Setup session
    session, runner = await setup_session_and_runner()

    # Sample queries
    demo_queries = [
        "What is the Pythagorean theorem?",
        "Explain the difference between speed and velocity",
        "How does photosynthesis work?",
        "What are quadratic equations?"
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
