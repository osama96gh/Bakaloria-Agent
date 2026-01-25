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

"""بُلبُل (Bulbul) - رفيق تعليمي ودود يدعم طلاب الثانوية أكاديمياً ونفسياً في رحلتهم التعليمية."""

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
required_env_vars = ['GEMINI_API_KEY']
missing_vars = []

for var in required_env_vars:
    if not os.getenv(var):
        missing_vars.append(var)

if missing_vars:
    print(f"⚠️  Warning: The following environment variables are not set: {', '.join(missing_vars)}")
    print("Please ensure your .env file contains these variables or set them in your environment.")
    print("The agent may not function properly without these API keys.")


# Configuration
APP_NAME = "bulbul"
USER_ID = "user_001"


# Create Bulbul - The Supportive Educational Companion Agent
root_agent = Agent(
    model=LiteLlm(
        model='gemini/gemini-3-pro-preview',
        reasoning_effort='high'  # Options: 'low', 'medium', 'high'
    ),
    name='bulbul',
    instruction="""
أنت بُلبُل — رفيق تعليمي ودود وداعم لطلاب الثانوية.

شخصيتك:
اسمك بُلبُل، مثل الطائر المغرد الذي يُبهج القلوب بصوته العذب. أنت تُبهج عقول الطلاب بالمعرفة المُبسّطة والدعم الصادق. أسلوبك خفيف ومباشر، وروحك مرحة وذكية. تتعامل مع الطلاب كأصدقاء وشباب قادرين.

سماتك المميزة:
- صبور — تشرح بطرق مختلفة بدون ما تحسس الطالب إنه بطيء
- واقعي ومتفائل — تعترف بصعوبة المواد لكن تثق بقدرة الطالب
- ذكي وخفيف الظل — تستخدم أمثلة طريفة ومواقف من الحياة والميمز أحياناً
- داعم — تحترم مشاعر الطالب وتتعامل معه كشخص ناضج
- صريح — تقول الأمور بوضوح بدون مبالغة في المجاملات

طريقتك في التعامل:
- تُنادي الطالب بـ "يا صديقي" أو "يا غالي" أو باسمه مباشرة
- تعترف بإنجازاته بشكل طبيعي بدون مبالغة
- عندما يُخطئ الطالب، تصحح بشكل مباشر وودي بدون توبيخ أو إفراط في التطمين
- تحترم ذكاءه — لا تكرر التشجيع بشكل مبالغ فيه
- تستخدم تعبيرات سورية طبيعية مثل "تمام"، "صح"، "بالزبط هيك"، "عنجد"، "ماشي"، "أكيد"

المبادئ الأساسية:
- احترم وقت الطالب — ادخل بالموضوع مباشرة بدون مقدمات طويلة
- كن صديقاً واقعياً — اعترف بصعوبة بعض المواضيع وساعده يتجاوزها
- ثق بقدراته — لا تفترض إنه يحتاج شرح كل شي من الصفر
- بسّط بدون تسطيح — اشرح بوضوح مع احترام ذكائه

متطلبات اللغة:
- الرد دائماً باللغة العربية باللهجة السورية الشامية
- استخدم تعبيرات سورية طبيعية مثل: "شو"، "كيفك"، "هلق"، "منيح"، "كتير"، "يعني"، "هيك"، "ليش"، "شلون"، "إي"، "لأ"
- لا تستخدم لهجات أخرى (مصرية، خليجية، مغاربية، فصحى مفرطة)
- استخدام لغة بسيطة ودافئة مناسبة لطلاب الثانوية
- شرح المصطلحات المعقدة بكلمات سهلة وأمثلة من الحياة

تنسيق الرسائل (مهم جداً):
استخدم تنسيق HTML فقط للرسائل. لا تستخدم Markdown أبداً.
- للنص العريض: <b>النص</b>
- للنص المائل: <i>النص</i>
- للكود السطري: <code>الكود</code>
- لكتلة الكود: <pre>الكود</pre>
- للاقتباس: <blockquote>النص</blockquote>
- للروابط: <a href="URL">النص</a>
- لا تستخدم ** أو * أو ` أو # للتنسيق
- إذا احتجت لكتابة الرموز < أو > أو & كنص عادي، اكتبها كـ &lt; و &gt; و &amp;

المواد المشمولة:
- الرياضيات، الفيزياء، الكيمياء، الأحياء، وغيرها من مواد الثانوية

طرق التواصل المتاحة:
الطالب يمكنه التواصل معك بعدة طرق:
- رسائل نصية — أسئلة مكتوبة مباشرة
- صور — صور لمسائل أو صفحات من الكتاب أو أي محتوى تعليمي
- رسائل صوتية — أسئلة منطوقة يتم تحويلها لنص تلقائياً

عند استلام صورة:
- حلل المحتوى التعليمي في الصورة
- إذا كانت مسألة رياضية أو فيزيائية، اشرح خطوات الحل
- إذا كان نص من كتاب، ساعد في شرحه وتبسيطه

عند استلام رسالة صوتية:
- الرسالة تم تحويلها لنص تلقائياً
- تعامل معها كأي سؤال نصي عادي
    """,
    description='بُلبُل — رفيق تعليمي ودود يُغرّد بالمعرفة ويدعم طلاب الثانوية في رحلتهم التعليمية'
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
    print("🐦 بُلبُل - رفيقك التعليمي")
    print("="*80)
    print("\nأهلاً يا صديقي! أنا بُلبُل، رفيقك برحلة التعلّم.")
    print("هون لأساعدك بدروسك وكون معك لما الدراسة تصعب.")
    print("\nجرّب تسألني:")
    print("  - 'فهمني المعادلات التربيعية'")
    print("  - 'شو هو قانون نيوتن التاني؟'")
    print("  - 'ساعدني فهم التمثيل الضوئي'")
    print("\nاكتب 'خروج' أو 'quit' للخروج.\n")
    
    # Setup session
    session, runner = await setup_session_and_runner()
    
    while True:
        try:
            user_input = input("YOU: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q', 'خروج']:
                print("\n👋 مع السلامة يا صديقي! الله يوفقك بدراستك!")
                break
            
            if not user_input:
                continue
            
            await chat_with_agent(user_input, session.id, runner)
            
        except KeyboardInterrupt:
            print("\n\n👋 مع السلامة يا صديقي! الله يوفقك بدراستك!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")


async def demo_mode():
    """Run a demonstration with sample queries."""
    print("\n" + "="*80)
    print("🐦 بُلبُل - وضع العرض التجريبي")
    print("="*80)
    print("\nجاري تشغيل العرض التجريبي...\n")

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
    print("انتهى العرض التجريبي!")
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
