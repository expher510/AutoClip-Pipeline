import os
import time
import json
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Setup Logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configure OpenAI Client
api_key = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")


client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key
)


def analyze_transcript(transcript):
    """Analyze transcript using OpenRouter via Env Key."""

    prompt = f"""
    You are an expert video editor and viral content strategist. 
    Your task is to identify the most engaging segments from the provided transcript 
    that are suitable for short-form video platforms like TikTok, Reels, and YouTube Shorts.
    
    **STRICT REQUIREMENTS:**
    1. **Duration**: duration MUST be between 60 seconds and 180 seconds (3 minutes)
    2. **Context Preservation**: Each segment must be a complete thought - no abrupt cuts
    3. **Sentence Boundaries**: Start at the beginning of a sentence, end at a natural conclusion
    4. **Meaning Coherence**: The clip must make sense on its own without requiring prior context
    
    **SELECTION CRITERIA:**
    - Strong hooks that grab attention 
    - Emotional moments, humor, or surprising revelations
    - Clear beginning, middle, and satisfying conclusion
    - High shareability potential
    
    **JSON OUTPUT FORMAT (REQUIRED):**
    {{
      "segments": [
        {{
          "start_time": <float, start time in seconds>,
          "end_time": <float, end time in seconds>,
          "duration": <float, duration in seconds (30-180)>,
          "description": "<string, brief summary of the clip content 10 words max>",
          "viral_score": <float, score from 0-10 indicating viral potential>,
          "reason": "<string, explanation of why this segment is engaging>"
        }}
      ]
    }}
    
    **IMPORTANT NOTES:**
    - If no suitable segments are found, return {{ "segments": [] }}
    - Ensure all strings are properly escaped
    - Each segment must be a complete, coherent thought
    - Avoid cutting mid-sentence or mid-thought
    
    Transcript to Analyze:
    {transcript}
    """

    max_retries = 3
    base_delay = 5
    content = None  # FIX: initialize content to avoid UnboundLocalError

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                extra_headers={
                    "HTTP-Referer": "https://github.com/Start-To-End-AI",
                    "X-Title": "Video Clipper AI",
                },
                temperature=0.7,
            )

            content = response.choices[0].message.content
            print(f"🤖 AI Raw Response (First 500 chars): {content[:500]}...")

            # Clean Markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            # Validate JSON and log segment count
            data = json.loads(content)
            segments_count = len(data.get("segments", []))
            print(f"🤖 AI Response parsed successfully: Found {segments_count} segments.")

            return {"content": content}

        except Exception as e:
            print(f"❌ Error in OpenRouter analysis: {e}")
            if attempt < max_retries - 1:
                wait_time = base_delay * (2 ** attempt)
                print(f"⚠️ Retrying task in {wait_time}s...")
                time.sleep(wait_time)
            else:
                break

    print("❌ All retry attempts failed.")
    return {"content": '{"segments": []}'}


# Smart chunking system for long transcripts
def smart_chunk_transcript(transcript, max_tokens=4000):
    """
    Split transcript into coherent chunks at sentence boundaries
    while preserving context and meaning.
    """
    import json
    # Simple sentence-based chunking
    sentences = transcript.replace('\n', ' ').split('. ')
    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        sentence_length = len(sentence.split())

        if current_length + sentence_length > max_tokens and current_chunk:
            chunk_text = '. '.join(current_chunk) + '.'
            chunks.append(chunk_text.strip())
            current_chunk = [sentence]
            current_length = sentence_length
        else:
            current_chunk.append(sentence)
            current_length += sentence_length

    if current_chunk:
        chunk_text = '. '.join(current_chunk) + '.'
        chunks.append(chunk_text.strip())

    return chunks


def analyze_transcript_with_chunking(transcript):
    """
    Analyze transcript using smart chunking for long content.
    Processes each chunk separately and merges results.
    """
    if len(transcript.split()) > 3000:
        logger.info("📦 Transcript too long, using smart chunking...")
        chunks = smart_chunk_transcript(transcript, max_tokens=3000)
        all_segments = []

        for i, chunk in enumerate(chunks):
            logger.info(f"🔄 Processing chunk {i+1}/{len(chunks)}...")
            result = analyze_transcript(chunk)

            try:
                data = json.loads(result['content'])
                if 'segments' in data:
                    all_segments.extend(data['segments'])
            except Exception as e:
                logger.warning(f"⚠️ Failed to parse chunk {i+1}: {e}")
                continue

        if all_segments:
            all_segments.sort(key=lambda x: x.get('viral_score', 0), reverse=True)
            unique_segments = []
            seen_times = set()

            for seg in all_segments:
                time_key = f"{seg.get('start_time', 0):.0f}-{seg.get('end_time', 0):.0f}"
                if time_key not in seen_times:
                    unique_segments.append(seg)
                    seen_times.add(time_key)

            return {"content": json.dumps({"segments": unique_segments[:10]})}

    return analyze_transcript(transcript)


# Testing
if __name__ == "__main__":
    test_transcript = """
    [0.0 - 5.0] Welcome to today's video about productivity hacks that actually work.
    [5.0 - 15.0] The first hack is something I call the 2-minute rule. If something takes less than 2 minutes, do it immediately.
    [15.0 - 30.0] This simple rule has transformed my life. I used to procrastinate on small tasks, but now I handle them right away.
    [30.0 - 45.0] The second hack is batching similar tasks together. Instead of checking email 20 times a day, I check it twice.
    [45.0 - 60.0] This has saved me hours every week. I batch my emails, phone calls, and even errands.
    [60.0 - 90.0] The third hack is the Pomodoro Technique. Work for 25 minutes, then take a 5-minute break.
    [90.0 - 120.0] This technique helps me stay focused and avoid burnout. I get more done in less time.
    """

    logger.info("🧪 Testing AI Analysis...")
    result = analyze_transcript_with_chunking(test_transcript)

    try:
        data = json.loads(result['content'])
        segments = data.get('segments', [])
        logger.info(f"✅ Found {len(segments)} viral segments:")

        for i, seg in enumerate(segments):
            logger.info(f"  #{i+1} [{seg['start_time']:.0f}s-{seg['end_time']:.0f}s] "
                        f"Score: {seg['viral_score']}/10 - {seg['description']}")
    except Exception as e:
        logger.error(f"❌ Error parsing result: {e}")
        logger.info(f"Raw result: {result}")