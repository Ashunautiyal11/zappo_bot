import os
from langchain_groq import ChatGroq
import tweepy
from logging import getLogger, basicConfig, INFO
import re
import random
import requests
from datetime import datetime
import time
import schedule
from dotenv import load_dotenv
from prompts import tweet_prompt

# Load .ENV variable
load_dotenv()

# Configure logging
basicConfig(
    level=INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = getLogger(__name__)

class TwitterBot:
    def __init__(self):
        self._init_apis()
        self._init_llm()
    
    def _init_apis(self):
        """Initialize API clients"""
        try:
            self.twitter_client = tweepy.Client(
                consumer_key=os.getenv('TWITTER_API_KEY'),
                consumer_secret=os.getenv('TWITTER_API_SECRET'),
                access_token=os.getenv('TWITTER_ACCESS_TOKEN'),
                access_token_secret=os.getenv('TWITTER_ACCESS_SECRET'),
                bearer_token=os.getenv('TWITTER_BEARER_TOKEN')
            )
            self.news_api_key = os.getenv('NEWS_API_KEY')
            logger.info("Successfully initialized API clients")
        except Exception as e:
            logger.error(f"Failed to initialize APIs: {e}")
            raise
    
    def _init_llm(self):
        """Initialize LLM"""
        try:
            self.llm = ChatGroq(
                model="mixtral-8x7b-32768",
                temperature=0.7,
                max_retries=2
            )
            logger.info("Successfully initialized LLM")
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            raise

    def extract_topics(self, title: str, description: str) -> str:
        """Extract meaningful topics from title and description using NLP-like approach"""
        # Combine title and description  
        full_text = f"{title} {description}"
        
        # Extract potential topic words (proper nouns and significant terms)
        # Look for capitalized words and words after specific markers
        topic_patterns = [
            r'\b[A-Z][a-zA-Z]+\b',  # Capitalized words
            r'(?:says|announces|confirms|reports)\s+([A-Z][a-zA-Z]+)',  # Words after news verbs
            r'(?:in|at|by)\s+([A-Z][a-zA-Z]+)'  # Words after prepositions
        ]
        
        topics = set()
        for pattern in topic_patterns:
            matches = re.findall(pattern, full_text)
            topics.update(matches)
        
        # Format as hashtags and filter by length
        hashtags = []
        for topic in topics:
            if len(topic) > 2: 
                hashtag = f"#{topic}"
                hashtags.append(hashtag)
        
        # Convert to string for prompt template
        return ' '.join(hashtags) if hashtags else "GeneralNews"

    def get_trending_news(self, limit: int = 5) -> list:
        """Get current trending news articles"""
        try:
            current_hour = datetime.now().strftime('%Y-%m-%d %H')
            today = datetime.now().strftime('%Y-%m-%d') 
            url = 'https://newsapi.org/v2/top-headlines'
            
            params = {
                'apiKey': self.news_api_key,
                'language': 'en',
                # 'country': 'in',
                'sortBy': 'popularity',
                'pageSize': limit,
                'from': today,
                'timestamp': current_hour
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                news_items = []
                
                for article in data.get('articles', []):
                    title = article.get('title', '')
                    description = article.get('description', '')
                    url = article.get('url', '')
                    published_at = article.get('publishedAt', '')
                    
                    if title and description:
                        # Extract topics for each news item
                        topics = self.extract_topics(title, description)
                        
                        news_context = {
                            'title': title,
                            'description': description,
                            'url': url,
                            'published_at': published_at,
                            'topics': topics, 
                            'full_context': f"{title}\n\n{description}",
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        news_items.append(news_context)
                
                logger.info(f"Successfully fetched {len(news_items)} trending news items")
                return news_items[:limit]
            else:
                logger.error(f"Failed to fetch news: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            return []

    def clean_text(self, text: str) -> str:
        """Clean text by removing unwanted characters and formatting"""
        text = re.sub(r'^content=[\'"]*', '', text)
        text = text.split('additional_kwargs=')[0]
        text = text.split('response_metadata=')[0]
        text = text.replace('\\n', ' ').replace('\\t', ' ')
        text = text.replace("\\'", "'").replace('\\"', '"')
        text = text.replace('\\', '')
        text = text.strip('"\'').strip()
        text = re.sub(r'\{.*?\}', '', text)
        return text

    def generate_tweet(self, news_item: dict) -> str:
        """Generate a tweet from a single news item"""
        try:
            # Create context with all required variables for the prompt
            context = {
                "title": news_item['title'],
                "description": news_item['description'],
                "topics": news_item['topics'] 
            }
            
            chain = tweet_prompt | self.llm
            response = chain.invoke(context)
            
            if hasattr(response, 'content'):
                content = response.content
            elif isinstance(response, dict):
                content = response.get('content', str(response))
            else:
                content = str(response)
            
            tweet = self.clean_text(content)
            return tweet
            
        except Exception as e:
            logger.error(f"Failed to generate tweet: {e}")
            raise

    def post_tweet(self, tweet_text: str) -> None:
        """Post a tweet using the Twitter API"""
        try:
            clean_tweet = self.clean_text(tweet_text)
            response = self.twitter_client.create_tweet(text=clean_tweet)
            # response = clean_tweet
            logger.info(f"Tweet posted successfully: {clean_tweet}")
            return response
        except Exception as e:
            logger.error(f"Failed to post tweet: {e}")
            raise

    def tweet_about_trend(self) -> None:
        """Get trending news and tweet about one item"""
        try:
            # Get top 5 trending news items
            news_items = self.get_trending_news(limit=5)
            if not news_items:
                logger.error("No news items available to tweet about")
                return
            
            # Select a random news item from top 5
            news_item = random.choice(news_items)
            
            # Log selected news item
            logger.info(f"Selected news item: {news_item['title']}")
            logger.info(f"Description: {news_item['description']}")
            logger.info(f"Topics: {news_item['topics']}")
            logger.info(f"Full context: {news_item['full_context']}")
            
            # Generate and post tweet
            tweet = self.generate_tweet(news_item)
            self.post_tweet(tweet)
            
        except Exception as e:
            logger.error(f"Failed to tweet about trend: {e}")
            raise

def run_bot():
    """Function to run the bot's main functionality"""
    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{current_time}] Running scheduled tweet...")
        
        bot = TwitterBot()
        
        # Print current news items with their context
        news_items = bot.get_trending_news()
        print("\nCurrent Trending News:")
        for idx, item in enumerate(news_items, start=1):
            print(f"{idx}. {item['title']}")
            print(f"   Description: {item['description']}")
            print(f"   Topics: {item['topics']}")
            print(f"   Published: {item.get('published_at', 'N/A')}")
            print(f"   Timestamp: {item['timestamp']}\n")
            
        bot.tweet_about_trend()
        
        print(f"Next tweet will be in 40 minutes...")
        
    except Exception as e:
        logger.error(f"Scheduled execution failed: {e}")

def main():
    """Main function to start the scheduled bot"""
    schedule.every(40).minutes.do(run_bot)
    run_bot()
    
    while True: 
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
