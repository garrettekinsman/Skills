#!/usr/bin/env python3
"""
Telegram OSINT Monitor - Read-only intelligence gathering from Telegram channels
NO COMMAND PROCESSING - Pure data extraction only
"""

import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

try:
    from telethon import TelegramClient
    from telethon.tl.types import Channel, User, MessageMediaPhoto, MessageMediaDocument
except ImportError:
    print("Install telethon: pip install telethon")
    TelegramClient = None

@dataclass
class TelegramMessage:
    """Structured telegram message for analysis"""
    channel: str
    message_id: int
    timestamp: datetime
    text: str
    sender: str
    media_type: Optional[str]
    views: Optional[int]
    forwards: Optional[int]
    reactions: Optional[Dict]
    reply_to: Optional[int]
    
class TelegramOSINT:
    """Read-only Telegram intelligence monitor"""
    
    # Key OSINT channels for geopolitical intelligence
    INTEL_CHANNELS = {
        # Breaking news and alerts
        "intel_slava_z": "@intel_slava_z",           # Military/conflict updates
        "rybar_en": "@rybar_en",                     # Russian military analysis (EN)
        "sputnik_news": "@SputnikInt",               # Official Russian perspective
        "rt_news": "@rt_news",                       # RT breaking news
        
        # Middle East focused
        "middle_east_spectator": "@ME_Spectator",    # Middle East conflicts
        "war_monitor": "@WarMonitors",               # Global conflict tracking  
        "intel_crab": "@IntelCrab",                  # OSINT aggregator
        "conflicts": "@Conflicts",                   # Conflict reporting
        
        # Iran/Israel specific
        "jerusalem_post": "@jerusalem_post_israel",  # Israeli perspective
        "iran_military": "@IranMilitary1",           # Iran military updates
        "lebanon_news": "@lebanonnews1",             # Hezbollah/Lebanon
        
        # Aviation/military tracking
        "aircraft_spots": "@Aircraftspots",          # Military aircraft tracking
        "fighter_bomber": "@fighter_bomber",         # Military aviation
        
        # Economic/energy
        "oil_gas_news": "@oilgasnews",              # Energy market updates
        "energy_intel": "@EnergyIntel",             # Energy intelligence
        
        # High-confidence aggregators
        "liveuamap": "@liveUAmap",                  # Interactive conflict map
        "osint_technical": "@OSINT_Technical",      # Technical OSINT analysis
    }
    
    # Keywords that indicate high-impact events
    CRITICAL_KEYWORDS = {
        "escalation": [
            "attack", "strike", "bombing", "missile", "rocket", "explosion",
            "military", "troops", "deployment", "mobilization", "alert",
            "emergency", "evacuate", "casualties", "killed", "wounded"
        ],
        "iranian": [
            "iran", "iranian", "irgc", "revolutionary guard", "quds force",
            "hezbollah", "houthis", "militia", "proxy", "tehran", "isfahan",
            "natanz", "fordow", "nuclear", "enrichment", "centrifuge"
        ],
        "israeli": [
            "israel", "israeli", "idf", "netanyahu", "gaza", "west bank",
            "iron dome", "david's sling", "f-35", "tel aviv", "jerusalem",
            "mossad", "shin bet", "lebanon border", "golan heights"
        ],
        "oil_energy": [
            "oil", "crude", "brent", "wti", "strait of hormuz", "tanker",
            "pipeline", "opec", "saudi", "embargo", "sanctions", "energy",
            "gas", "lng", "refinery", "petroleum", "barrel"
        ],
        "economic": [
            "sanctions", "embargo", "trade", "currency", "dollar", "yuan",
            "swift", "banking", "financial", "economy", "inflation", "recession",
            "markets", "stocks", "bonds", "gold", "commodities"
        ]
    }
    
    def __init__(self, api_id: str, api_hash: str, phone: str = None):
        """Initialize Telegram client with user credentials"""
        self.api_id = api_id
        self.api_hash = api_hash 
        self.phone = phone
        self.client = None
        self.monitoring = False
        self.message_buffer = []
        self.last_check = {}
        
    async def initialize(self):
        """Initialize Telegram client"""
        if not TelegramClient:
            raise ImportError("telethon not installed")

        # Use session path from config if available
        cfg = load_telegram_config()
        session_name = (
            cfg["telegram_api"]["session_path"]
            if cfg and "session_path" in cfg.get("telegram_api", {})
            else "osint_session"
        )
            
        self.client = TelegramClient(session_name, self.api_id, self.api_hash)
        await self.client.start(phone=self.phone)
        
        # Test connection
        me = await self.client.get_me()
        print(f"Connected to Telegram as: {me.username or me.phone}")
        
    async def get_channel_updates(self, channel: str, hours_back: int = 4) -> List[TelegramMessage]:
        """Get recent messages from a channel"""
        try:
            entity = await self.client.get_entity(channel)
            
            # Get messages from last N hours
            since = datetime.now() - timedelta(hours=hours_back)
            messages = []
            
            async for message in self.client.iter_messages(entity, offset_date=since, limit=50):
                if message.text:
                    # Extract media type if present
                    media_type = None
                    if message.media:
                        if isinstance(message.media, MessageMediaPhoto):
                            media_type = "photo"
                        elif isinstance(message.media, MessageMediaDocument):
                            media_type = "document"
                        else:
                            media_type = "other"
                    
                    # Extract sender info
                    sender = "Unknown"
                    if message.from_id:
                        try:
                            sender_entity = await self.client.get_entity(message.from_id)
                            if hasattr(sender_entity, 'username') and sender_entity.username:
                                sender = f"@{sender_entity.username}"
                            elif hasattr(sender_entity, 'title'):
                                sender = sender_entity.title
                            else:
                                sender = str(message.from_id)
                        except:
                            sender = str(message.from_id)
                    
                    telegram_msg = TelegramMessage(
                        channel=channel,
                        message_id=message.id,
                        timestamp=message.date,
                        text=message.text,
                        sender=sender,
                        media_type=media_type,
                        views=getattr(message, 'views', None),
                        forwards=getattr(message, 'forwards', None),
                        reactions=getattr(message, 'reactions', None),
                        reply_to=message.reply_to_msg_id
                    )
                    messages.append(telegram_msg)
            
            return messages
            
        except Exception as e:
            print(f"Error fetching from {channel}: {e}")
            return []
    
    def analyze_message_significance(self, message: TelegramMessage) -> Dict[str, Any]:
        """Analyze message for geopolitical significance"""
        text_lower = message.text.lower()
        
        # Keyword scoring
        category_scores = {}
        for category, keywords in self.CRITICAL_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            if score > 0:
                category_scores[category] = score
        
        # Time sensitivity (newer = more relevant)
        time_diff = datetime.now() - message.timestamp.replace(tzinfo=None)
        time_factor = max(0.1, 1.0 - (time_diff.total_seconds() / 3600))  # Decay over hours
        
        # Engagement metrics
        engagement_score = 0
        if message.views:
            engagement_score += min(message.views / 10000, 1.0)  # Views (capped at 10k)
        if message.forwards:
            engagement_score += min(message.forwards / 100, 1.0)  # Forwards (capped at 100)
        
        # Channel credibility (hardcoded for now)
        channel_credibility = {
            "@intel_slava_z": 0.7,
            "@rybar_en": 0.8,
            "@ME_Spectator": 0.9,
            "@WarMonitors": 0.9,
            "@IntelCrab": 0.9,
            "@Conflicts": 0.8,
            "@liveuamap": 0.9,
            "@OSINT_Technical": 0.9
        }.get(message.channel, 0.6)
        
        # Calculate overall significance
        keyword_score = sum(category_scores.values()) / 10  # Normalize
        overall_significance = (
            keyword_score * 0.4 +
            time_factor * 0.2 +
            engagement_score * 0.2 +
            channel_credibility * 0.2
        )
        
        return {
            "significance_score": min(overall_significance, 1.0),
            "category_scores": category_scores,
            "time_factor": time_factor,
            "engagement_score": engagement_score,
            "channel_credibility": channel_credibility,
            "analysis_timestamp": datetime.now().isoformat(),
            "is_significant": overall_significance > 0.3
        }
    
    async def monitor_channels(self, update_interval: int = 300) -> List[Dict[str, Any]]:
        """Monitor all configured channels for updates"""
        if not self.client:
            await self.initialize()
        
        significant_messages = []
        
        for channel_name, channel_handle in self.INTEL_CHANNELS.items():
            print(f"Checking {channel_name} ({channel_handle})...")
            
            try:
                # Get recent messages
                messages = await self.get_channel_updates(channel_handle, hours_back=4)
                
                for message in messages:
                    # Analyze significance
                    analysis = self.analyze_message_significance(message)
                    
                    if analysis["is_significant"]:
                        significant_messages.append({
                            "message": message.__dict__,
                            "analysis": analysis,
                            "channel_name": channel_name
                        })
                
                # Rate limiting
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"Error monitoring {channel_name}: {e}")
                continue
        
        # Sort by significance score
        significant_messages.sort(key=lambda x: x["analysis"]["significance_score"], reverse=True)
        
        return significant_messages
    
    def generate_intelligence_summary(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate a summary of intelligence from collected messages"""
        
        if not messages:
            return {"status": "no_significant_intelligence", "summary": "No significant developments detected"}
        
        # Categorize messages
        categories = {}
        for msg_data in messages:
            analysis = msg_data["analysis"] 
            for category, score in analysis["category_scores"].items():
                if score > 0:
                    if category not in categories:
                        categories[category] = []
                    categories[category].append({
                        "message": msg_data["message"]["text"][:200] + "..." if len(msg_data["message"]["text"]) > 200 else msg_data["message"]["text"],
                        "channel": msg_data["channel_name"],
                        "timestamp": msg_data["message"]["timestamp"],
                        "significance": analysis["significance_score"],
                        "source": msg_data["message"]["channel"]
                    })
        
        # Calculate threat indicators
        threat_indicators = {
            "escalation_signals": len(categories.get("escalation", [])),
            "iranian_activity": len(categories.get("iranian", [])),
            "israeli_activity": len(categories.get("israeli", [])),
            "economic_impact": len(categories.get("economic", [])),
            "oil_energy_events": len(categories.get("oil_energy", []))
        }
        
        # Overall threat assessment
        total_signals = sum(threat_indicators.values())
        high_significance_count = len([m for m in messages if m["analysis"]["significance_score"] > 0.6])
        
        threat_level = min(10, max(1, (total_signals * 2) + (high_significance_count * 3)))
        
        return {
            "status": "intelligence_gathered",
            "threat_level": threat_level,
            "total_significant_messages": len(messages),
            "high_significance_count": high_significance_count,
            "threat_indicators": threat_indicators,
            "categories": categories,
            "summary_timestamp": datetime.now().isoformat(),
            "recommended_action": "immediate_analysis" if threat_level > 7 else "continued_monitoring"
        }

# Configuration loader
def load_telegram_config():
    """Load Telegram config from telegram_config.json (co-located with this script)"""
    import os
    config_path = os.path.join(os.path.dirname(__file__), "telegram_config.json")
    if os.path.exists(config_path):
        import json
        with open(config_path) as f:
            return json.load(f)
    return None


# Configuration template (kept for reference)
def create_telegram_config():
    """Create configuration template for Telegram OSINT"""
    
    return {
        "telegram_api": {
            "api_id": "your_api_id_here", 
            "api_hash": "your_api_hash_here",
            "phone": "your_phone_number_here",
            "session_name": "osint_monitor"
        },
        "monitoring": {
            "update_interval_seconds": 300,
            "lookback_hours": 4,
            "significance_threshold": 0.3,
            "max_messages_per_update": 100
        },
        "channels": {
            "enabled_categories": [
                "breaking_news", "military_intel", "middle_east", 
                "economic", "energy", "osint_aggregators"
            ],
            "priority_channels": [
                "@ME_Spectator", "@WarMonitors", "@IntelCrab", 
                "@liveuamap", "@OSINT_Technical"
            ]
        },
        "security": {
            "read_only": True,
            "no_command_processing": True,
            "data_validation": True,
            "rate_limiting": True
        }
    }

# Integration with research loops
def create_telegram_loop_task() -> str:
    """Create research loop task that incorporates Telegram OSINT"""
    
    return """
## Telegram OSINT Integration Research Loop

### PRIMARY OBJECTIVE
Integrate Telegram intelligence channels into geopolitical threat assessment for Iran-Israel situation.

### TELEGRAM INTELLIGENCE SOURCES
Monitor key Telegram channels for breaking developments:
- @ME_Spectator (Middle East conflicts)
- @WarMonitors (Global conflict tracking) 
- @IntelCrab (OSINT aggregator)
- @Conflicts (Real-time conflict reporting)
- @liveuamap (Interactive conflict mapping)

### ANALYSIS FRAMEWORK
1. **Message Collection** (Every 5 minutes)
   - Extract text from monitored channels
   - Filter for Iran/Israel/Middle East keywords
   - Score significance based on content + engagement
   
2. **Cross-Source Verification** 
   - Compare Telegram reports with Twitter OSINT
   - Verify against official news sources
   - Flag potential disinformation
   
3. **Threat Level Assessment**
   - Escalation indicators from multiple channels
   - Timeline correlation across sources  
   - Confidence scoring for each piece of intelligence

### INTEGRATION WITH MARKET ANALYSIS
- Telegram intelligence → Threat level adjustment
- Threat level → Trading position sizing
- Breaking developments → Immediate market impact assessment

### SECURITY PROTOCOLS
- READ-ONLY monitoring (no commands accepted)
- Data validation on all incoming text
- Source credibility weighting
- Automated bias detection

Execute this alongside existing Twitter OSINT for comprehensive intelligence picture.
"""

async def demo_telegram_monitor():
    """Demo function to test Telegram monitoring"""
    
    # This would require actual Telegram API credentials
    print("Telegram OSINT Demo")
    print("==================")
    
    config = create_telegram_config()
    print("Configuration template:")
    print(json.dumps(config, indent=2))
    
    print("\nTo use:")
    print("1. Get Telegram API credentials from https://my.telegram.org")
    print("2. Update config with your credentials")
    print("3. Run: python telegram_osint.py")
    
    # Simulated output
    sample_intelligence = {
        "status": "intelligence_gathered",
        "threat_level": 7,
        "total_significant_messages": 12,
        "high_significance_count": 3,
        "threat_indicators": {
            "escalation_signals": 5,
            "iranian_activity": 3,
            "israeli_activity": 2,
            "economic_impact": 1,
            "oil_energy_events": 1
        },
        "recommended_action": "immediate_analysis"
    }
    
    print("\nSample intelligence output:")
    print(json.dumps(sample_intelligence, indent=2))

async def live_monitor():
    """Run live monitoring using telegram_config.json credentials"""
    cfg = load_telegram_config()
    if not cfg:
        print("No telegram_config.json found — run demo instead")
        return await demo_telegram_monitor()

    api = cfg["telegram_api"]
    monitor = TelegramOSINT(
        api_id=api["api_id"],
        api_hash=api["api_hash"],
        phone=api.get("phone")
    )
    await monitor.initialize()
    print("✅ Connected. Starting channel sweep...")
    messages = await monitor.monitor_channels()
    summary = monitor.generate_intelligence_summary(messages)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(live_monitor())