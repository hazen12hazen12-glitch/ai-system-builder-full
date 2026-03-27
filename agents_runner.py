#!/usr/bin/env python3
"""
ملف واحد يجمع جميع الوكلاء (أكثر من 30 وكيلاً) مع جميع التحسينات والإضافات النهائية.
يتم استدعاؤه عبر سطر الأوامر:
    python3 agents_runner.py <agent_name> <project_id> [user_description]

المفاتيح المطلوبة في ملف .env (ضعها قبل التشغيل):
- GROQ_API_KEYS: مفاتيح Groq مفصولة بفواصل
- GROQ_API_KEY: مفتاح واحد (إذا لم توجد GROQ_API_KEYS)
- HF_API_TOKEN: مفتاح Hugging Face (اختياري)
- SUPABASE_ACCESS_TOKENS, RENDER_API_KEYS, GITHUB_TOKENS, CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, KOYEB_API_KEYS
- REDIS_URL, WEAVIATE_URL (اختياري)
- AGENT_TIMEOUT_SEC
"""

import os
import sys
import asyncio
import json
import logging
import hashlib
import random
import shutil
import subprocess
import tempfile
import time
import gzip
import smtplib
from email.mime.text import MIMEText
from logging.handlers import RotatingFileHandler
from typing import Dict, Any, Optional, List, Tuple
import httpx
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

# ---------- إعدادات أساسية ----------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("agents_runner")
file_handler = RotatingFileHandler("agents_runner.log", maxBytes=10_000_000, backupCount=5)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = None
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Redis connected")
except Exception as e:
    logger.warning(f"Redis connection failed: {e}")

# Groq
GROQ_API_KEYS = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()]
if not GROQ_API_KEYS and os.getenv("GROQ_API_KEY"):
    GROQ_API_KEYS = [os.getenv("GROQ_API_KEY")]
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-70b-8192")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Hugging Face
HF_API_TOKEN = os.getenv("HF_API_TOKEN")
HF_MODEL = os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.1")
HF_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}"

MAX_RETRIES = 3
BASE_DELAY = 1.0

# إعدادات البريد الإلكتروني (للإشعارات)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
DEFAULT_EMAIL = os.getenv("DEFAULT_EMAIL", "user@example.com")

# ---------- دالات مساعدة إضافية ----------
async def validate_groq_keys() -> List[str]:
    valid = []
    for key in GROQ_API_KEYS:
        headers = {"Authorization": f"Bearer {key}"}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
                if resp.status_code == 200:
                    valid.append(key)
                else:
                    logger.warning(f"Invalid Groq key: {key[:10]}...")
        except Exception:
            logger.warning(f"Groq key {key[:10]}... unreachable")
    return valid

async def send_email_notification(project_id: str, user_email: str = None):
    if not EMAIL_USER or not EMAIL_PASS:
        logger.warning("Email credentials not set, skipping notification")
        return
    to = user_email or DEFAULT_EMAIL
    msg = MIMEText(f"Your project {project_id} has been completed successfully.")
    msg['Subject'] = f"Project {project_id} completed"
    msg['From'] = EMAIL_USER
    msg['To'] = to
    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        logger.info(f"Notification sent to {to} for project {project_id}")
    except Exception as e:
        logger.warning(f"Failed to send email: {e}")

# ---------- BaseAgent (الفئة الأساسية مع جميع التحسينات) ----------
class BaseAgent:
    def __init__(self, name: str, system_message: str, tenant_id: Optional[str] = None,
                 enable_cache: bool = True, retry_attempts: int = 3, retry_delay_base: float = 1.0):
        self.name = name
        self.system_message = system_message
        self.tenant_id = tenant_id
        self.enable_cache = enable_cache
        self.retry_attempts = retry_attempts
        self.retry_delay_base = retry_delay_base
        self.logger = logging.getLogger(f"agent.{name}")
        self._groq_key_index = 0

    def _get_tenant_key(self, key: str) -> str:
        return f"tenant:{self.tenant_id}:{key}" if self.tenant_id else key

    async def _cache_get(self, key: str) -> Optional[str]:
        if not self.enable_cache or redis_client is None:
            return None
        try:
            return await redis_client.get(self._get_tenant_key(key))
        except Exception:
            return None

    async def _cache_set(self, key: str, value: str, expire_sec: int = 86400):
        if not self.enable_cache or redis_client is None:
            return
        try:
            await redis_client.set(self._get_tenant_key(key), value, ex=expire_sec)
        except Exception:
            pass

    async def write_output(self, filename: str, content: str, subdir: str = "") -> None:
        path = f"{subdir}/{filename}" if subdir else filename
        if len(content) > 1_000_000:
            compressed = gzip.compress(content.encode())
            await self._cache_set(f"file:{path}", compressed, expire_sec=7*86400)
            await self._emit_event("file_created_compressed", {"path": path, "size": len(compressed)})
        else:
            await self._cache_set(f"file:{path}", content, expire_sec=7*86400)
            await self._emit_event("file_created", {"path": path, "content_preview": content[:200]})

    async def read_input(self, filename: str, subdir: str = "") -> Optional[str]:
        path = f"{subdir}/{filename}" if subdir else filename
        data = await self._cache_get(f"file:{path}")
        if data is None:
            self.logger.warning(f"File not found: {path}")
            return None
        if isinstance(data, bytes) and data[:2] == b'\x1f\x8b':
            return gzip.decompress(data).decode()
        return data

    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        if redis_client is None:
            return
        try:
            channel = f"tenant:{self.tenant_id}:events"
            event = {
                "type": event_type,
                "agent": self.name,
                "timestamp": datetime.utcnow().isoformat(),
                "data": data
            }
            await redis_client.publish(channel, json.dumps(event))
        except Exception as e:
            self.logger.warning(f"Failed to emit event: {e}")

    async def _call_groq(self, prompt: str) -> Tuple[str, str]:
        if not GROQ_API_KEYS:
            raise Exception("No Groq API keys available")
        start_idx = self._groq_key_index
        for offset in range(len(GROQ_API_KEYS)):
            idx = (start_idx + offset) % len(GROQ_API_KEYS)
            key = GROQ_API_KEYS[idx]
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": self.system_message},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 4096
            }
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(GROQ_URL, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        self._groq_key_index = (idx + 1) % len(GROQ_API_KEYS)
                        return data["choices"][0]["message"]["content"], "groq"
                    elif resp.status_code == 429:
                        wait = 60 + random.uniform(0, 10)
                        self.logger.warning(f"Rate limited on key {idx}. Waiting {wait:.1f}s")
                        await asyncio.sleep(wait)
                        continue
                    else:
                        self.logger.warning(f"Groq key {idx} failed: {resp.status_code}")
            except Exception as e:
                self.logger.warning(f"Groq key {idx} exception: {e}")
        raise Exception("All Groq keys exhausted")

    async def _call_huggingface(self, prompt: str) -> Tuple[str, str]:
        if not HF_API_TOKEN:
            raise Exception("HF_API_TOKEN not set")
        headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
        formatted = f"<s>[INST] {self.system_message}\n\n{prompt} [/INST]"
        payload = {"inputs": formatted, "parameters": {"max_new_tokens": 4096, "temperature": 0.2}}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(HF_URL, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    text = data[0].get("generated_text", "")
                else:
                    text = data.get("generated_text", "")
                return text, "huggingface"
            else:
                raise Exception(f"HF error {resp.status_code}: {resp.text}")

    async def call_model(self, prompt: str, operation_name: str = "call") -> str:
        if not prompt:
            raise ValueError("Prompt cannot be empty")
        if await self.is_cancelled():
            raise Exception("Project cancelled by user")
        cache_key = f"cache:{hashlib.sha256(prompt.encode()).hexdigest()}"
        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        providers = [("groq", self._call_groq), ("huggingface", self._call_huggingface)]
        last_error = None
        for provider_name, provider_func in providers:
            for attempt in range(1, self.retry_attempts + 1):
                try:
                    result, used = await provider_func(prompt)
                    await self._cache_set(cache_key, result)
                    return result
                except Exception as e:
                    self.logger.warning(f"{provider_name} attempt {attempt} failed: {e}")
                    last_error = e
                    if attempt < self.retry_attempts:
                        delay = self.retry_delay_base * (2 ** (attempt - 1)) + random.uniform(0, 1)
                        await asyncio.sleep(delay)
                    else:
                        break
        raise Exception(f"All providers failed: {last_error}")

    async def generate_with_review(self, prompt: str, reviewer_agent: "ReviewerAgent",
                                   max_iterations: int = 5, quality_threshold: float = 0.95,
                                   timeout_sec: int = 300) -> str:
        start_time = time.time()
        current = await self.call_model(prompt, "generate")
        iteration = 1
        while iteration <= max_iterations and (time.time() - start_time) < timeout_sec:
            await self._emit_event("review_started", {"iteration": iteration})
            review = await reviewer_agent.review(current, prompt, self.name)
            score = review.get("score", 0.0)
            feedback = review.get("feedback", "")
            await self._emit_event("review_completed", {"iteration": iteration, "score": score, "feedback_preview": feedback[:200]})
            if score >= quality_threshold:
                return current
            improvement = f"""المحتوى الأصلي:\n{current}\n\nملاحظات المراجعة:\n{feedback}\n\nالرجاء تحسين المحتوى وفقًا للملاحظات."""
            current = await self.call_model(improvement, "improve")
            iteration += 1
        self.logger.warning(f"generate_with_review finished after {iteration-1} iterations (timeout/time limit)")
        return current

    async def request_approval(self, action_description: str, payload: Dict[str, Any], timeout_sec: int = 300) -> bool:
        if redis_client is None:
            return False
        request_id = f"approval_{self.tenant_id}_{datetime.utcnow().timestamp()}"
        channel = f"tenant:{self.tenant_id}:approvals"
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel)
        await redis_client.publish(channel, json.dumps({
            "request_id": request_id, "agent": self.name,
            "action": action_description, "payload": payload, "tenant": self.tenant_id
        }))
        start = datetime.utcnow()
        while (datetime.utcnow() - start).total_seconds() < timeout_sec:
            msg = await pubsub.get_message(ignore_subscribe_messages=True)
            if msg:
                data = json.loads(msg["data"])
                if data.get("request_id") == request_id:
                    await pubsub.unsubscribe(channel)
                    return data.get("approved", False)
            await asyncio.sleep(1)
        await pubsub.unsubscribe(channel)
        return False

    async def acquire_project_lock(self, timeout_sec: int = 300) -> bool:
        if redis_client is None:
            return True
        lock_key = f"lock:{self.tenant_id}"
        return await redis_client.set(lock_key, "locked", nx=True, ex=timeout_sec)

    async def release_project_lock(self):
        if redis_client is None:
            return
        await redis_client.delete(f"lock:{self.tenant_id}")

    async def save_state(self, stage: str, data: Dict[str, Any]):
        if redis_client is None:
            return
        key = f"project:{self.tenant_id}:state"
        state = await redis_client.get(key) or "{}"
        state = json.loads(state)
        state[stage] = data
        await redis_client.set(key, json.dumps(state), ex=7*86400)

    async def load_state(self) -> Dict[str, Any]:
        if redis_client is None:
            return {}
        key = f"project:{self.tenant_id}:state"
        data = await redis_client.get(key)
        return json.loads(data) if data else {}

    async def is_cancelled(self) -> bool:
        if redis_client is None:
            return False
        return await redis_client.get(f"cancel:{self.tenant_id}") == "1"

    async def cancel_project(self):
        if redis_client is not None:
            await redis_client.set(f"cancel:{self.tenant_id}", "1", ex=86400)

    async def cleanup_project(self) -> None:
        if redis_client is None or not self.tenant_id:
            return
        try:
            keys = await redis_client.keys(f"tenant:{self.tenant_id}:*")
            if keys:
                await redis_client.delete(*keys)
            self.logger.info(f"Cleaned up project {self.tenant_id}")
        except Exception as e:
            self.logger.warning(f"Cleanup failed: {e}")

    @staticmethod
    async def health_check() -> Dict[str, Any]:
        redis_ok = False
        if redis_client:
            try:
                await redis_client.ping()
                redis_ok = True
            except:
                pass
        return {"status": "healthy" if (redis_ok and GROQ_API_KEYS) else "unhealthy",
                "redis": redis_ok, "groq_keys": len(GROQ_API_KEYS), "timestamp": datetime.utcnow().isoformat()}

    async def with_project(self, project_id: str):
        return self.__class__(name=self.name, system_message=self.system_message, tenant_id=project_id,
                              enable_cache=self.enable_cache, retry_attempts=self.retry_attempts,
                              retry_delay_base=self.retry_delay_base)


# ---------- وكلاء أساسيون (PM, Architect, UI/UX, Backend, Android, iOS, Windows, macOS, Linux, Database, QA, Security, Docs, Integration, Video, Analytics) ----------
class PMAgent(BaseAgent):
    def __init__(self, tenant_id: str = None, **kwargs):
        super().__init__(
            name="PM_Agent",
            system_message="""أنت مدير مشاريع خبير. مهمتك:
1. تحليل طلب المستخدم واستخراج المتطلبات الوظيفية وغير الوظيفية.
2. تقسيم المشروع إلى مهام فرعية مع تحديد الأولويات والتبعيات.
3. تقدير الوقت والموارد اللازمة.
4. إخراج النتائج بصيغة JSON منظمة.""",
            tenant_id=tenant_id,
            **kwargs
        )
    async def analyze(self, user_input: str) -> str:
        result = await self.call_model(user_input, "analyze")
        await self.write_output("requirements.txt", result, subdir="pm")
        return result

class ArchitectAgent(BaseAgent):
    def __init__(self, tenant_id: str = None, **kwargs):
        super().__init__(
            name="Architect_Agent",
            system_message="""أنت مهندس معماري خبير. بناءً على المتطلبات:
1. اختر التقنيات المناسبة (لغات، أطر، قواعد بيانات) لكل منصة.
2. صمم البنية العامة (Microservices, Monolithic, Serverless).
3. حدد واجهات التواصل (REST, GraphQL, WebSockets).""",
            tenant_id=tenant_id,
            **kwargs
        )
    async def design(self) -> str:
        req = await self.read_input("requirements.txt", subdir="pm")
        if not req:
            return "Error: requirements.txt not found"
        result = await self.call_model(req, "design")
        await self.write_output("architecture.txt", result, subdir="architect")
        return result

class UIUXAgent(BaseAgent):
    def __init__(self, tenant_id: str = None, **kwargs):
        super().__init__(
            name="UI_UX_Agent",
            system_message="""أنت مصمم واجهات خبير. بناءً على المتطلبات والتصميم المعماري:
1. أنشئ أكواد واجهات أولية (HTML/CSS، XML، SwiftUI، XAML) حسب المنصة.
2. تأكد من التوافق مع إرشادات كل منصة (Material Design, HIG).""",
            tenant_id=tenant_id,
            **kwargs
        )
    async def design_ui(self) -> str:
        req = await self.read_input("requirements.txt", subdir="pm")
        arch = await self.read_input("architecture.txt", subdir="architect")
        if not req or not arch:
            return "Error: requirements or architecture not found"
        combined = f"المتطلبات:\n{req}\n\nالتصميم المعماري:\n{arch}"
        result = await self.call_model(combined, "design_ui")
        await self.write_output("ui_codes.txt", result, subdir="ui_ux")
        return result

class BackendAgent(BaseAgent):
    def __init__(self, tenant_id: str = None, **kwargs):
        super().__init__(
            name="Backend_Agent",
            system_message="""أنت مطور Backend خبير. بناءً على المتطلبات والتصميم المعماري:
1. اكتب كود الخادم باستخدام إطار عمل مناسب (FastAPI، Express، إلخ).
2. أنشئ واجهات برمجة التطبيقات (REST/GraphQL).
3. نفذ منطق الأعمال وأمان المصادقة.""",
            tenant_id=tenant_id,
            **kwargs
        )
    async def generate_backend(self) -> str:
        req = await self.read_input("requirements.txt", subdir="pm")
        arch = await self.read_input("architecture.txt", subdir="architect")
        if not req or not arch:
            return "Error: requirements or architecture not found"
        combined = f"المتطلبات:\n{req}\n\nالتصميم المعماري:\n{arch}"
        result = await self.call_model(combined, "backend")
        await self.write_output("backend_code.txt", result, subdir="backend")
        return result

class AndroidAgent(BaseAgent):
    def __init__(self, tenant_id: str = None, **kwargs):
        super().__init__(
            name="Android_Agent",
            system_message="""أنت مطور أندرويد خبير. بناءً على المتطلبات والتصميم المعماري:
1. اكتب كود Kotlin/Java باستخدام Jetpack Compose.
2. أنشئ ملفات التهيئة (Gradle) اللازمة.""",
            tenant_id=tenant_id,
            **kwargs
        )
    async def generate_android(self) -> str:
        req = await self.read_input("requirements.txt", subdir="pm")
        arch = await self.read_input("architecture.txt", subdir="architect")
        if not req or not arch:
            return "Error: require
