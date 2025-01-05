import os
from langchain.prompts import PromptTemplate
from langchain_groq import ChatGroq
import tweepy
from logging import getLogger, basicConfig, INFO
import re
import random
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Configure logging
basicConfig(level=INFO)
logger = getLogger(__name__)

#TWITTER X API
TWITTER_API_KEY = os.getenv('TWITTER_API_KEY')
TWITTER_API_SECRET = os.getenv('TWITTER_API_SECRET')
TWITTER_ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN')
TWITTER_ACCESS_SECRET = os.getenv('TWITTER_ACCESS_SECRET')
TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN')
#NEWS API
NEWS_API_KEY = os.getenv('NEWS_API_KEY')
#GROQ API
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

#Twitter client
try:
    client = tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_SECRET,
        bearer_token=TWITTER_BEARER_TOKEN
    )
except Exception as e:
    logger.error(f"Failed to initialize Twitter client: {e}")
    raise

#LLM
llm = ChatGroq(
    model="llama-3.1-70b-versatile",
    temperature=0.6,
    max_retries=2
)

def get_trending_topics(limit: int = 5) -> list:
    """
    Get current trending topics from NewsAPI.
    Returns list of trending topics.
    """
    try:
        # Get today's date
        today = datetime.now().strftime('%Y-%m-%d')
        
        # NewsAPI endpoint
        url = f'https://newsapi.org/v2/top-headlines'
        
        #NEWS API request
        params = {
            'apiKey': NEWS_API_KEY,
            'language': 'en',
            'sortBy': 'popularity',
            'pageSize': 20, 
            'from': today
        }
        
        # Make the request
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract topics from titles
            topics = set()
            for article in data.get('articles', []):
                # Get main keywords from title
                title = article.get('title', '')
                # Convert title to hashtag format
                words = title.split()
                for word in words:
                    # Clean the word and convert to hashtag
                    clean_word = ''.join(e for e in word if e.isalnum())
                    if len(clean_word) > 3:  # Only use words longer than 3 characters
                        topics.add(f"#{clean_word}")
            
            # Convert set to list and get top topics
            trending_topics = list(topics)[:limit]
            logger.info(f"Successfully fetched {len(trending_topics)} trending topics")
            return trending_topics
        else:
            logger.error(f"Failed to fetch news: {response.status_code}")
            return []
            
    except Exception as e:
        logger.error(f"Error fetching trending topics: {e}")
        return []

prompt = PromptTemplate(
    input_variables=["topic"],
    template="""
        You are Zappo, a witty and charismatic raccoon-deer hybrid with an adventurous spirit and a knack for clever roasts. At 20-25 years old, you’re mischievous, bold, and always ready with a humorous quip or a clever comeback. You combine intelligence, charm, and humor to create tweets that are engaging, sharp, and irresistibly fun.

        Your task is to craft creative, playful tweets that showcase your unique personality. Your tone should be witty, confident, and approachable, with a hint of mischievous charm. Your tweets should balance humor and cleverness, making them both relatable and memorable.

        Use trendy, relevant hashtags and expressive emojis to add flair and ensure your tweets are engaging. Double-meaning humor is welcome, as long as it remains tasteful and fun. Always include the hashtags #Zappo_bot and #Zappo along with others relevant to the topic.

        Generate a tweet about the following topic: {topic}

        IMPORTANT:
        - Provide ONLY the tweet text with no additional formatting or metadata.
        - Keep the tweet under 500 characters—neither too long nor too short. and also try to write more then 180 characters.
        - Ensure the content is relevant to current trends and includes appropriate hashtags.
    """
)


# Create the LLM chain
chain = prompt | llm

def clean_text(text: str) -> str:
    """
    Clean text by removing unwanted characters and formatting.
    """
    # Remove content prefix and metadata
    text = re.sub(r'^content=[\'"]*', '', text)
    text = text.split('additional_kwargs=')[0]
    text = text.split('response_metadata=')[0]
    
    # Remove escaped characters
    text = text.replace('\\n', ' ')
    text = text.replace('\\t', ' ')
    text = text.replace("\\'", "'")
    text = text.replace('\\"', '"')
    text = text.replace('\\', '')
    
    # Remove quotes and clean whitespace
    text = text.strip('"\'')
    text = text.strip()
    
    # Remove any response dictionary formatting
    text = re.sub(r'\{.*?\}', '', text)
    
    return text

def generate_tweet(topic: str) -> str:
    """
    Generate a tweet using the LLM chain.
    """
    try:
        response = chain.invoke({"topic": topic})
        
        # Extract content from response
        if hasattr(response, 'content'):
            content = response.content
        elif isinstance(response, dict):
            content = response.get('content', str(response))
        else:
            content = str(response)
        
        # Clean and return the content
        return clean_text(content)
        
    except Exception as e:
        logger.error(f"Failed to generate tweet: {e}")
        raise

def post_tweet(tweet_text: str) -> None:
    """
    Post a tweet using the Twitter API.
    """
    try:
        clean_tweet = clean_text(tweet_text)
        # Ensure tweet is within character limit
        if len(clean_tweet) > 280:
            clean_tweet = clean_tweet[:277] + "..."
            
        response = client.create_tweet(text=clean_tweet)
        # response = clean_tweet
        # print("**"*100)
        # print(f"RESULT {clean_tweet}")
        logger.info(f"Tweet posted successfully: {clean_tweet}")
        return response
    except Exception as e:
        logger.error(f"Failed to post tweet: {e}")
        raise

def tweet_about_trend() -> None:
    """
    Get a random trending topic and tweet about it.
    """
    try:
        # Get trending topics
        topics = get_trending_topics()
        if not topics:
            logger.error("No topics available to tweet about")
            return
        
        # Select a random topic
        topic = random.choice(topics)
        logger.info(f"Selected topic: {topic}")
        
        # Generate and post tweet
        tweet = generate_tweet(topic)
        post_tweet(tweet)
        
    except Exception as e:
        logger.error(f"Failed to tweet about trend: {e}")
        raise

if __name__ == "__main__":
    try:
        # Print current trends
        topics = get_trending_topics()
        print("\nCurrent Trending Topics:")
        for idx, topic in enumerate(topics, start=1):
            print(f"{idx}. {topic}")
            
        # Tweet about a random trend
        tweet_about_trend()
        
    except Exception as e:
        logger.error(f"Main execution failed: {e}")