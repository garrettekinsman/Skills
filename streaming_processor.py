#!/usr/bin/env python3
"""
Real-time streaming processor for research loops
Handles continuous data ingestion and event-driven loop updates
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Any, AsyncGenerator, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import aiohttp
import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StreamType(Enum):
    """Types of data streams"""
    PRICE_FEED = "price_feed"
    NEWS_FEED = "news_feed"
    SYSTEM_METRICS = "system_metrics"
    USER_BEHAVIOR = "user_behavior"
    SOCIAL_SENTIMENT = "social_sentiment"
    WEB_SCRAPE = "web_scrape"
    API_ENDPOINT = "api_endpoint"

@dataclass
class StreamConfig:
    """Configuration for a data stream"""
    name: str
    stream_type: StreamType
    source_url: str
    update_frequency: int  # seconds
    significance_threshold: float
    filters: Dict[str, Any] = field(default_factory=dict)
    transform: Optional[str] = None  # Python code to transform data
    
@dataclass
class StreamEvent:
    """A single event from a data stream"""
    timestamp: float
    stream_name: str
    data: Dict[str, Any]
    significance_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

class StreamProcessor:
    """Main streaming processor for research loops"""
    
    def __init__(self, loop_id: str, domain: str):
        self.loop_id = loop_id
        self.domain = domain
        self.streams: Dict[str, StreamConfig] = {}
        self.active_connections = {}
        self.event_buffer = asyncio.Queue()
        self.significance_threshold = 0.10
        self.running = False
        self.callbacks: List[Callable] = []
        
    def add_stream(self, config: StreamConfig):
        """Add a data stream to monitor"""
        self.streams[config.name] = config
        logger.info(f"Added stream: {config.name} ({config.stream_type.value})")
    
    def add_callback(self, callback: Callable[[StreamEvent], None]):
        """Add callback for significant events"""
        self.callbacks.append(callback)
    
    async def start_streaming(self):
        """Start all configured streams"""
        self.running = True
        logger.info(f"Starting streaming for loop {self.loop_id}")
        
        # Start each stream as a separate task
        tasks = []
        for stream_config in self.streams.values():
            if stream_config.stream_type == StreamType.PRICE_FEED:
                task = asyncio.create_task(self._stream_prices(stream_config))
            elif stream_config.stream_type == StreamType.NEWS_FEED:
                task = asyncio.create_task(self._stream_news(stream_config))
            elif stream_config.stream_type == StreamType.SYSTEM_METRICS:
                task = asyncio.create_task(self._stream_metrics(stream_config))
            elif stream_config.stream_type == StreamType.API_ENDPOINT:
                task = asyncio.create_task(self._stream_api(stream_config))
            else:
                logger.warning(f"Unsupported stream type: {stream_config.stream_type}")
                continue
            
            tasks.append(task)
        
        # Start event processor
        processor_task = asyncio.create_task(self._process_events())
        tasks.append(processor_task)
        
        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop_streaming(self):
        """Stop all streams"""
        self.running = False
        logger.info(f"Stopping streaming for loop {self.loop_id}")
        
        # Close active connections
        for conn in self.active_connections.values():
            if hasattr(conn, 'close'):
                await conn.close()
        self.active_connections.clear()
    
    async def _stream_prices(self, config: StreamConfig):
        """Stream financial price data"""
        while self.running:
            try:
                # Example: Poll Tradier API for price updates
                symbols = config.filters.get('symbols', ['SPY'])
                async with aiohttp.ClientSession() as session:
                    for symbol in symbols:
                        async with session.get(
                            f"https://api.tradier.com/v1/markets/quotes?symbols={symbol}",
                            headers={"Authorization": f"Bearer {config.filters.get('api_key')}"}
                        ) as response:
                            if response.status == 200:
                                data = await response.json()
                                
                                # Calculate significance (price change %)
                                quotes = data.get('quotes', {}).get('quote', {})
                                if isinstance(quotes, list):
                                    quotes = quotes[0] if quotes else {}
                                
                                change_pct = abs(quotes.get('change_percentage', 0))
                                significance = change_pct / 100  # Convert to decimal
                                
                                event = StreamEvent(
                                    timestamp=time.time(),
                                    stream_name=config.name,
                                    data={'symbol': symbol, **quotes},
                                    significance_score=significance
                                )
                                
                                await self.event_buffer.put(event)
                
            except Exception as e:
                logger.error(f"Error in price stream {config.name}: {e}")
            
            await asyncio.sleep(config.update_frequency)
    
    async def _stream_news(self, config: StreamConfig):
        """Stream news and sentiment data"""
        while self.running:
            try:
                # Example: Brave Search for latest news
                query = config.filters.get('query', 'market news')
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"https://api.search.brave.com/res/v1/web/search?q={query}&count=5&freshness=pd",
                        headers={"X-Subscription-Token": config.filters.get('api_key')}
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            # Calculate significance based on result count and freshness
                            results = data.get('web', {}).get('results', [])
                            significance = min(len(results) / 10, 1.0)
                            
                            event = StreamEvent(
                                timestamp=time.time(),
                                stream_name=config.name,
                                data={'query': query, 'results': results},
                                significance_score=significance
                            )
                            
                            await self.event_buffer.put(event)
                
            except Exception as e:
                logger.error(f"Error in news stream {config.name}: {e}")
            
            await asyncio.sleep(config.update_frequency)
    
    async def _stream_metrics(self, config: StreamConfig):
        """Stream system metrics (Prometheus, etc.)"""
        while self.running:
            try:
                # Example: Poll Prometheus metrics
                metric_url = config.source_url
                async with aiohttp.ClientSession() as session:
                    async with session.get(metric_url) as response:
                        if response.status == 200:
                            data = await response.text()
                            
                            # Parse Prometheus format and calculate significance
                            # This is simplified - real implementation would parse properly
                            lines = data.split('\n')
                            metrics = {}
                            for line in lines:
                                if line and not line.startswith('#'):
                                    parts = line.split(' ')
                                    if len(parts) >= 2:
                                        metrics[parts[0]] = float(parts[1])
                            
                            # Example significance calculation
                            cpu_usage = metrics.get('cpu_usage_percent', 0)
                            significance = max(0, (cpu_usage - 50) / 50)  # Significant if >50%
                            
                            event = StreamEvent(
                                timestamp=time.time(),
                                stream_name=config.name,
                                data=metrics,
                                significance_score=significance
                            )
                            
                            await self.event_buffer.put(event)
                
            except Exception as e:
                logger.error(f"Error in metrics stream {config.name}: {e}")
            
            await asyncio.sleep(config.update_frequency)
    
    async def _stream_api(self, config: StreamConfig):
        """Stream from generic API endpoint"""
        while self.running:
            try:
                headers = config.filters.get('headers', {})
                async with aiohttp.ClientSession() as session:
                    async with session.get(config.source_url, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            # Apply custom transform if specified
                            if config.transform:
                                try:
                                    # Execute the transform code
                                    exec_globals = {'data': data, 'time': time}
                                    exec(config.transform, exec_globals)
                                    data = exec_globals.get('result', data)
                                except Exception as e:
                                    logger.error(f"Transform error in {config.name}: {e}")
                            
                            # Calculate significance using specified logic or default
                            significance_field = config.filters.get('significance_field')
                            if significance_field and significance_field in data:
                                significance = float(data[significance_field])
                            else:
                                significance = 0.5  # Default moderate significance
                            
                            event = StreamEvent(
                                timestamp=time.time(),
                                stream_name=config.name,
                                data=data,
                                significance_score=significance
                            )
                            
                            await self.event_buffer.put(event)
                
            except Exception as e:
                logger.error(f"Error in API stream {config.name}: {e}")
            
            await asyncio.sleep(config.update_frequency)
    
    async def _process_events(self):
        """Process events from the buffer and trigger callbacks"""
        while self.running:
            try:
                # Wait for an event (with timeout to check running status)
                event = await asyncio.wait_for(self.event_buffer.get(), timeout=1.0)
                
                # Check if event meets significance threshold
                if event.significance_score >= self.significance_threshold:
                    logger.info(f"Significant event: {event.stream_name} "
                              f"(score: {event.significance_score:.3f})")
                    
                    # Trigger all callbacks
                    for callback in self.callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(event)
                            else:
                                callback(event)
                        except Exception as e:
                            logger.error(f"Callback error: {e}")
                
            except asyncio.TimeoutError:
                continue  # Check running status
            except Exception as e:
                logger.error(f"Event processing error: {e}")

# Domain-specific stream configurations

FINANCIAL_STREAMS = {
    "market_prices": StreamConfig(
        name="market_prices",
        stream_type=StreamType.PRICE_FEED,
        source_url="https://api.tradier.com/v1/markets/quotes",
        update_frequency=30,  # 30 seconds
        significance_threshold=0.02,  # 2% price move
        filters={"symbols": ["SPY", "QQQ", "VIX"]}
    ),
    "market_news": StreamConfig(
        name="market_news", 
        stream_type=StreamType.NEWS_FEED,
        source_url="https://api.search.brave.com/res/v1/web/search",
        update_frequency=300,  # 5 minutes
        significance_threshold=0.3,
        filters={"query": "stock market breaking news"}
    )
}

TECHNICAL_STREAMS = {
    "system_health": StreamConfig(
        name="system_health",
        stream_type=StreamType.SYSTEM_METRICS,
        source_url="http://localhost:9090/api/v1/query?query=up",
        update_frequency=60,  # 1 minute
        significance_threshold=0.1,
        filters={"alert_threshold": 0.9}
    ),
    "github_activity": StreamConfig(
        name="github_activity",
        stream_type=StreamType.API_ENDPOINT,
        source_url="https://api.github.com/repos/{owner}/{repo}/events",
        update_frequency=300,  # 5 minutes
        significance_threshold=0.2,
        filters={"headers": {"Accept": "application/vnd.github.v3+json"}}
    )
}

def create_domain_streams(domain: str, custom_config: Dict[str, Any] = None) -> Dict[str, StreamConfig]:
    """Create appropriate streams for a domain"""
    if domain == "financial":
        streams = FINANCIAL_STREAMS.copy()
    elif domain == "technical":
        streams = TECHNICAL_STREAMS.copy()
    else:
        streams = {}
    
    # Apply custom configuration
    if custom_config:
        for name, config_updates in custom_config.items():
            if name in streams:
                # Update existing stream config
                for key, value in config_updates.items():
                    setattr(streams[name], key, value)
    
    return streams

async def main():
    """Demo/test the streaming processor"""
    processor = StreamProcessor("demo_loop", "financial")
    
    # Add demo streams
    streams = create_domain_streams("financial")
    for stream in streams.values():
        processor.add_stream(stream)
    
    # Add callback to print significant events
    def print_event(event: StreamEvent):
        print(f"SIGNIFICANT EVENT: {event.stream_name}")
        print(f"  Time: {time.ctime(event.timestamp)}")
        print(f"  Score: {event.significance_score:.3f}")
        print(f"  Data: {json.dumps(event.data, indent=2)[:200]}...")
        print()
    
    processor.add_callback(print_event)
    
    try:
        await processor.start_streaming()
    except KeyboardInterrupt:
        print("Stopping...")
        await processor.stop_streaming()

if __name__ == "__main__":
    asyncio.run(main())