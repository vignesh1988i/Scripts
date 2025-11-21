# mq_chatbot.py → Run with: chainlit run mq_chatbot.py -w
import chainlit as cl
import time
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import os
from langchain_ollama import ChatOllama
from langchain.memory import ConversationBufferWindowMemory
from tools import tools

# ──────────────────────────────────────────────────────────────
# Configuration & Constants
# ──────────────────────────────────────────────────────────────
load_dotenv()
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")
LOGIN_URL = f"{FASTAPI_URL}{os.getenv('LOGIN_ENDPOINT', '/login')}"
LAST_ACTIVITY = "last_activity"
TOKEN_KEY = "jwt_token"
TOKEN_EXPIRES_AT = "token_expires_at"

# ──────────────────────────────────────────────────────────────
# Automatically add JWT Bearer token to ALL requests in tools.py
# ──────────────────────────────────────────────────────────────
original_post = requests.post
def authenticated_post(url, *args, **kwargs):
    token = cl.user_session.get(TOKEN_KEY)
    if token:
        headers = kwargs.get("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers
    return original_post(url, *args, **kwargs)
requests.post = authenticated_post   # Monkey patch — clean & safe

# ──────────────────────────────────────────────────────────────
# Login function — called once per session
# ──────────────────────────────────────────────────────────────
async def login(username: str, password: str) -> str:
    """Get JWT token from your FastAPI /login endpoint"""
    try:
        resp = requests.post(LOGIN_URL, json={"username": username, "password": password}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            raise ValueError("No access_token in response")
        return token
    except Exception as e:
        raise ValueError(f"Login failed: {str(e)}")

# ──────────────────────────────────────────────────────────────
# On chat start — force login with nice form
# ──────────────────────────────────────────────────────────────
@cl.on_chat_start
async def start():
    # If already logged in (browser refresh), skip login
    if cl.user_session.get(TOKEN_KEY):
        await cl.Message(content="Session active – MQ-Genie ready").send()
        await setup_bot()
        return

    await cl.Message(content="**MQ-Genie requires authentication**").send()

    # Beautiful login form
    response = await cl.AskUserMessage(
        content="Please enter your MQ API credentials:",
        timeout=300
    ).send()

    if not response:
        await cl.Message(content="Timeout. Goodbye.").send()
        return

    username = response.get("username")
    password = response.get("password")

    if not username or not password:
        await cl.Message(content="Both fields required.").send()
        return

    try:
        await cl.Message(content="Authenticating...").send()
        token = await login(username, password)

        # Store token + expiry
        cl.user_session.set(TOKEN_KEY, token)
        expires_in = int(os.getenv("TOKEN_EXPIRY_MINUTES", "30"))
        cl.user_session.set(TOKEN_EXPIRES_AT, datetime.now() + timedelta(minutes=expires_in))

        await cl.Message(content=f"Login successful!\nWelcome, {username.split('@')[0]}").send()
        await setup_bot()
    except Exception as e:
        await cl.Message(content=f"Login failed: {e}").send()

# ──────────────────────────────────────────────────────────────
# Setup LLM + memory after successful login
# ──────────────────────────────────────────────────────────────
async def setup_bot():
    llm = ChatOllama(model="llama3.1:70b", temperature=0.1)  # or :8b
    llm_with_tools = llm.bind_tools(tools)
    memory = ConversationBufferWindowMemory(k=10, return_messages=True)

    await cl.Message(content="""
**MQ-Genie Secure** is ready!
• Ask anything about queues, channels, connections
• Data is live from your authenticated FastAPI
• Session auto-refreshes after 15 mins inactivity
""").send()

    cl.user_session.set("llm", llm_with_tools)
    cl.user_session.set("memory", memory)
    cl.user_session.set(LAST_ACTIVITY, time.time())

# ──────────────────────────────────────────────────────────────
# Token expiry check
# ──────────────────────────────────────────────────────────────
async def check_token_valid() -> bool:
    expires_at = cl.user_session.get(TOKEN_EXPIRES_AT)
    if expires_at and datetime.now() > expires_at:
        await cl.Message(content="Session expired. Please log in again.").send()
        cl.user_session.clear()
        await start()
        return False
    return True

# ──────────────────────────────────────────────────────────────
# Main message handler
# ──────────────────────────────────────────────────────────────
@cl.on_message
async def main(message: cl.Message):
    if not cl.user_session.get(TOKEN_KEY):
        await cl.Message(content="Please log in first.").send()
        return

    if not await check_token_valid():
        return

    # Auto-refresh after 15 mins inactivity
    now = time.time()
    if (now - cl.user_session.get(LAST_ACTIVITY, calculated_now)) > 15*60:
        await cl.Message(content="Refreshed – fetching latest live data").send()
        memory = cl.user_session.get("memory")
        memory.chat_memory.messages = memory.chat_memory.messages[-4:]

    cl.user_session.set(LAST_ACTIVITY, time.time())

    # Build full context
    msgs = [{"role": "system", "content": "You are MQ-Genie. Be crisp. Always require Queue Manager. Use tools."}]
    for m in cl.user_session.get("memory").chat_memory.messages:
        msgs.append({"role": m.type, "content": m.content})
    msgs.append({"role": "user", "content": message.content})

    response = await cl.user_session.get("llm").ainvoke(msgs, config={"callbacks": [cl.LangchainCallbackHandler()]})

    # Tool execution with error handling
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            for t in tools:
                if t.name == tc["name"]:
                    try:
                        result = t.invoke(tc["args"])
                        ts = datetime.now().strftime("%H:%M:%S")
                        await cl.Message(content=f"[{ts}] → {result}").send()
                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code == 401:
                            await cl.Message(content="Token expired. Re-logging in...").send()
                            cl.user_session.set(TOKEN_KEY, None)
                            await start()
                        else:
                            await cl.Message(content=f"API Error {e.response.status_code}: {e.response.text}").send()
                    except Exception as e:
                        await cl.Message(content=f"Tool failed: {str(e)}").send()
                    break
    else:
        await cl.Message(content=response.content.strip()).send()

    # Save conversation
    cl.user_session.get("memory").save_context({"input": message.content}, {"output": response.content or ""})
