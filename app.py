import os
import uuid
import random
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from ddgs import DDGS
from transformers import pipeline
from urllib.parse import urljoin, urlparse

# --- Initialization & AI Model Loading ---
app = Flask(__name__)
if not os.path.exists('static'):
    os.makedirs('static')

print("Loading AI models...")
summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")
print("AI models loaded.")

translation_pipelines = {}
language_map = {
    "fr": "French", "es": "Spanish", "de": "German", "ru": "Russian", 
    "zh": "Chinese", "ja": "Japanese", "ar": "Arabic", "hi": "Hindi", 
    "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "en": "English"
}

# Explicit mapping to prevent model not found errors
TRANSLATION_MODELS = {
    "fr": "Helsinki-NLP/opus-mt-en-fr", "es": "Helsinki-NLP/opus-mt-en-es",
    "de": "Helsinki-NLP/opus-mt-en-de", "ru": "Helsinki-NLP/opus-mt-en-ru",
    "zh": "Helsinki-NLP/opus-mt-en-zh", "ja": "Helsinki-NLP/opus-mt-en-ja",
    "ar": "Helsinki-NLP/opus-mt-en-ar", "hi": "Helsinki-NLP/opus-mt-en-hi",
    "it": "Helsinki-NLP/opus-mt-en-it", "pt": "Helsinki-NLP/opus-mt-en-pt",
    "nl": "Helsinki-NLP/opus-mt-en-nl",
}

# --- Main Application Route ---
@app.route('/')
def index():
    return render_template('index.html', languages=language_map)

# --- Route 1: "Scout a Topic" ---
@app.route('/process', methods=['POST'])
def process():
    data = request.json
    query = data.get('query')
    selected_languages = data.get('languages', ['en'])
    if not query: return jsonify({"error": "Query cannot be empty."}), 400

    try:
        top_sites = []
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=10))
            if not results: return jsonify({"error": f"No search results found for '{query}'."}), 404
            
            best_content = find_best_content(results, query)
            if not best_content: return jsonify({"error": "Could not extract readable content from top search results."}), 500
            
            for r in results:
                top_sites.append({
                    "title": r.get('title', 'No Title Available'), 
                    "link": r.get('href', '#'),
                    "snippet": r.get('body', 'No snippet available.'), 
                    "rating": random.randint(3, 5),
                    "visits": f"{random.randint(5, 500)}k", 
                    "logo": find_logo(r.get('href'))
                })

        summary = generate_summary(best_content)
        if not summary: return jsonify({"error": "Failed to generate summary."}), 500
        
        translations = generate_translations(summary, selected_languages)
        return jsonify({'summary': summary, 'translations': translations, 'top_sites': top_sites})

    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

# --- Route 2: "Summarize Text" ---
@app.route('/summarize-text', methods=['POST'])
def summarize_text_route():
    data = request.json
    text_to_summarize = data.get('text', '')
    selected_languages = data.get('languages', ['en'])
    if not text_to_summarize: return jsonify({"error": "Text to summarize cannot be empty."}), 400

    try:
        summary = generate_summary(text_to_summarize)
        if not summary: return jsonify({"error": "Failed to generate summary from the provided text."}), 500
        translations = generate_translations(summary, selected_languages)
        return jsonify({'summary': summary, 'translations': translations})
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

# --- Route 3: "Scout from URL" ---
@app.route('/scrape-url', methods=['POST'])
def scrape_url_route():
    data = request.json
    url = data.get('url')
    selected_languages = data.get('languages', ['en'])
    if not url: return jsonify({"error": "URL cannot be empty."}), 400
    
    try:
        scraped_text = scrape_url_for_text(url)
        if not scraped_text: return jsonify({"error": "Could not extract readable content from the URL."}), 500

        summary = generate_summary(scraped_text)
        if not summary: return jsonify({"error": "Failed to generate summary from the URL."}), 500
        
        translations = generate_translations(summary, selected_languages)
        return jsonify({'summary': summary, 'translations': translations})
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

# --- Helper Functions ---
def find_best_content(results, query):
    best_content = ""
    highest_score = 0
    for result in results[:4]:
        try:
            content = scrape_url_for_text(result['href'])
            if content:
                keyword_count = content.lower().count(query.lower())
                score = len(content) + (keyword_count * 500)
                if score > highest_score:
                    highest_score = score
                    best_content = content
        except Exception as e:
            print(f"Could not analyze {result['href']}: {e}")
            continue
    return best_content

def find_logo(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        icon_rel = ['icon', 'shortcut icon', 'apple-touch-icon']
        for rel in icon_rel:
            link_tag = soup.find('link', rel=rel)
            if link_tag and link_tag.get('href'): return urljoin(url, link_tag['href'])
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'): return urljoin(url, og_image['content'])
        parsed_url = urlparse(url)
        favicon_url = f"{parsed_url.scheme}://{parsed_url.netloc}/favicon.ico"
        if requests.head(favicon_url, timeout=2).status_code == 200: return favicon_url
    except Exception: pass
    return None

def scrape_url_for_text(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    paragraphs = soup.find_all('p')
    return ' '.join([p.get_text() for p in paragraphs if len(p.get_text()) > 50])

def generate_summary(text):
    text = text[:4000]
    summary_result = summarizer(text, max_length=300, min_length=100, do_sample=False)
    return summary_result[0]['summary_text'] if summary_result else None

def generate_translations(summary_text, languages):
    translations = {}
    for lang_code in languages:
        if lang_code == "en":
            translations[lang_code] = {'text': summary_text}
            continue
        
        model_name = TRANSLATION_MODELS.get(lang_code)
        if not model_name: continue

        if lang_code not in translation_pipelines:
            print(f"Loading translation model for '{lang_code}'...")
            translation_pipelines[lang_code] = pipeline("translation", model=model_name)
        
        translator = translation_pipelines[lang_code]
        translation_result = translator(summary_text, max_length=512)
        if translation_result:
            translations[lang_code] = {'text': translation_result[0]['translation_text']}
    return translations

if __name__ == '__main__':
    app.run(debug=True, port=5050)
