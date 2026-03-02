#!/usr/bin/env python3
"""
Telegram + Twitter OSINT Integration for Research Loops
Combines Telegram channels with Twitter monitoring for comprehensive intelligence
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
from telegram_osint import TelegramOSINT
from geopolitical_trading_strategies import GeopoliticalTrader

class MultiSourceOSINT:
    """Combine Telegram and Twitter OSINT for comprehensive intelligence"""
    
    def __init__(self, telegram_config: Dict[str, Any] = None):
        self.telegram_monitor = None
        if telegram_config:
            self.telegram_monitor = TelegramOSINT(
                telegram_config["api_id"],
                telegram_config["api_hash"], 
                telegram_config.get("phone")
            )
        
        self.trader = GeopoliticalTrader()
        self.intelligence_cache = []
        
    async def gather_multi_source_intelligence(self) -> Dict[str, Any]:
        """Gather intelligence from all available sources"""
        
        intelligence_report = {
            "timestamp": datetime.now().isoformat(),
            "sources": {},
            "consolidated_assessment": {},
            "market_implications": {},
            "recommended_trades": {}
        }
        
        # 1. Telegram Intelligence (if available)
        if self.telegram_monitor:
            try:
                await self.telegram_monitor.initialize()
                telegram_messages = await self.telegram_monitor.monitor_channels()
                telegram_summary = self.telegram_monitor.generate_intelligence_summary(telegram_messages)
                
                intelligence_report["sources"]["telegram"] = {
                    "status": "operational",
                    "messages_analyzed": len(telegram_messages),
                    "threat_indicators": telegram_summary.get("threat_indicators", {}),
                    "threat_level": telegram_summary.get("threat_level", 0),
                    "key_developments": telegram_summary.get("categories", {})
                }
                
            except Exception as e:
                intelligence_report["sources"]["telegram"] = {
                    "status": "error",
                    "error": str(e)
                }
        
        # 2. Twitter OSINT Queries (for research loop integration)
        twitter_queries = [
            "Iran Israel military OR strike OR retaliation OR IRGC",
            "Strait Hormuz OR oil tanker OR naval OR blockade", 
            "Hezbollah OR proxy OR militia OR rocket OR missile",
            "Netanyahu Iran OR nuclear OR red line OR ultimatum",
            "BREAKING OR URGENT Iran Israel OR Middle East"
        ]
        
        intelligence_report["sources"]["twitter"] = {
            "status": "configured",
            "queries": twitter_queries,
            "note": "Execute via Grok model in research loop"
        }
        
        # 3. Market Data Integration
        # This would integrate with Tradier API for live market data
        market_indicators = {
            "oil_premium": "Monitor WTI/Brent vs normal range",
            "vix_elevation": "Current VIX vs 20 baseline", 
            "defense_performance": "XLE, RTX, LMT relative strength",
            "safe_haven_flows": "GLD, TLT, DXY movements"
        }
        
        intelligence_report["sources"]["market"] = {
            "status": "configured",
            "indicators": market_indicators,
            "note": "Pull live data via Tradier API"
        }
        
        # 4. Consolidated Threat Assessment
        telegram_threat = intelligence_report["sources"].get("telegram", {}).get("threat_level", 0)
        
        # Combine all threat indicators
        consolidated_threat = min(10, telegram_threat)  # Will add other sources
        
        intelligence_report["consolidated_assessment"] = {
            "overall_threat_level": consolidated_threat,
            "confidence": "medium" if telegram_threat > 0 else "low",
            "primary_concerns": self._extract_primary_concerns(intelligence_report),
            "timeline_assessment": self._assess_timeline(intelligence_report)
        }
        
        # 5. Market Implications
        market_impact = self.trader.iran_escalation_trades(consolidated_threat, "2_weeks")
        intelligence_report["market_implications"] = market_impact
        
        return intelligence_report
    
    def _extract_primary_concerns(self, intel_report: Dict) -> List[str]:
        """Extract primary concerns from multi-source intelligence"""
        concerns = []
        
        telegram_data = intel_report["sources"].get("telegram", {})
        if telegram_data.get("status") == "operational":
            indicators = telegram_data.get("threat_indicators", {})
            
            if indicators.get("escalation_signals", 0) > 3:
                concerns.append("Multiple escalation signals detected")
            if indicators.get("iranian_activity", 0) > 2:
                concerns.append("Increased Iranian military activity")
            if indicators.get("oil_energy_events", 0) > 1:
                concerns.append("Energy/oil supply concerns")
        
        if not concerns:
            concerns = ["Routine monitoring - no major concerns"]
            
        return concerns
    
    def _assess_timeline(self, intel_report: Dict) -> Dict[str, str]:
        """Assess timeline for potential developments"""
        
        telegram_threat = intel_report["sources"].get("telegram", {}).get("threat_level", 0)
        
        if telegram_threat >= 8:
            return {
                "next_24h": "High probability of significant development",
                "next_week": "Sustained escalation likely",
                "resolution_timeframe": "Weeks to months"
            }
        elif telegram_threat >= 6:
            return {
                "next_24h": "Moderate risk of escalation",
                "next_week": "Situation likely to evolve",
                "resolution_timeframe": "Days to weeks"
            }
        else:
            return {
                "next_24h": "Low risk of major developments", 
                "next_week": "Continued monitoring required",
                "resolution_timeframe": "Ongoing diplomatic process"
            }
    
    def generate_research_loop_prompt(self) -> str:
        """Generate comprehensive research loop prompt with all sources"""
        
        return """
## Multi-Source Geopolitical Intelligence Research Loop

### INTELLIGENCE COLLECTION FRAMEWORK

**Source 1: Telegram OSINT** (READ-ONLY monitoring)
- Key channels: @ME_Spectator, @WarMonitors, @IntelCrab, @Conflicts, @liveuamap
- Focus: Real-time conflict updates, military movements, breaking developments
- Analysis: Automated significance scoring, cross-channel verification
- Security: No command processing, pure data extraction

**Source 2: Twitter OSINT** (via Grok model)  
- Key accounts: @sentdefender, @IntelCrab, @WarMonitors, @ElintNews
- Search queries: Iran Israel military, Strait Hormuz, Hezbollah proxy, IRGC activity
- Analysis: Sentiment tracking, narrative analysis, rumor verification

**Source 3: Market Intelligence** (via Tradier API)
- Oil prices: WTI, Brent crude futures and ETFs
- Defense sector: RTX, LMT, NOC, ITA performance  
- Safe havens: GLD, TLT, VIX, DXY movements
- Risk assets: QQQ, emerging markets, volatility

### ANALYSIS PROTOCOLS

**Cross-Source Verification**
- Minimum 2 independent sources for any claim
- Weight sources by historical credibility
- Flag potential disinformation campaigns
- Time-correlation of reports across platforms

**Threat Level Calibration**
- 1-3: Routine diplomatic activity
- 4-6: Economic measures, military posturing
- 7-8: Proxy conflicts, limited strikes  
- 9-10: Direct confrontation, supply disruption

**Market Impact Assessment**
- Historical precedent analysis (Soleimani 2020, Tanker War 1987)
- Sector rotation implications (energy up, tech down)
- Volatility regime prediction (VIX trajectory)
- Currency/commodity flow analysis

### INTEGRATION WITH EXISTING TRADES

Current positions that benefit from Iran escalation:
- XLE $55/$57 call spread (energy momentum) 
- QQQ $605/$600 put spread (risk-off hedge)
- XLV $155/$160 call spread (defensive rotation)

Assess if additional hedges needed based on threat level.

### OUTPUT REQUIREMENTS

1. **Executive Summary** (threat level, key developments, timeline)
2. **Source Analysis** (Telegram + Twitter + Market data synthesis)
3. **Trade Recommendations** (position adjustments, new hedges if threat >7)
4. **Monitoring Plan** (key indicators, update triggers)

### EXECUTION INSTRUCTIONS

- Use Grok model for Twitter data extraction and sentiment analysis
- Integrate Telegram intelligence if available (manual input if needed)
- Cross-reference all claims against multiple source types
- Focus on actionable intelligence with clear market implications
- Update every 4-6 hours unless major developments trigger immediate update

**This is a live intelligence operation with real money at risk.**
**Accuracy, timeliness, and bias resistance are critical.**
"""

def create_telegram_setup_guide() -> str:
    """Create setup guide for Telegram OSINT integration"""
    
    return """
# Telegram OSINT Setup Guide

## Security-First Approach
This setup provides **READ-ONLY** access to Telegram channels for intelligence gathering.
**NO COMMAND PROCESSING** - purely data extraction for research loops.

## Prerequisites

### 1. Telegram API Credentials
Visit: https://my.telegram.org
- Login with your phone number
- Go to "API development tools"
- Create new application:
  - App title: "OSINT Monitor"
  - App short name: "osint_mon"
  - Platform: Desktop
- Copy `api_id` and `api_hash`

### 2. Install Dependencies
```bash
pip install telethon
# Or add to your virtual environment
```

### 3. Configuration
Create `telegram_config.json` (git-ignored):
```json
{
  "api_id": "your_api_id_here",
  "api_hash": "your_api_hash_here", 
  "phone": "+1234567890",
  "session_name": "osint_readonly"
}
```

### 4. Test Connection
```python
from telegram_osint import TelegramOSINT
import asyncio

async def test():
    monitor = TelegramOSINT("api_id", "api_hash", "phone")
    await monitor.initialize()
    messages = await monitor.monitor_channels()
    print(f"Found {len(messages)} significant messages")

asyncio.run(test())
```

## Key Intelligence Channels

### Tier 1 (Highest credibility)
- @ME_Spectator - Middle East conflicts
- @WarMonitors - Global conflict tracking
- @IntelCrab - OSINT aggregator
- @liveuamap - Interactive conflict mapping

### Tier 2 (Regional focus)
- @Conflicts - Real-time conflict reporting
- @OSINT_Technical - Technical analysis
- @Aircraftspots - Military aviation tracking

### Tier 3 (Perspective sources)  
- @intel_slava_z - Military updates
- @rybar_en - Russian analysis
- @SputnikInt - Official Russian view

## Integration with Research Loops

### Option 1: Manual Integration
1. Run Telegram monitor separately
2. Copy significant intelligence into research loop prompt
3. Cross-reference with Twitter OSINT

### Option 2: Automated Integration
1. Configure telegram_config.json
2. Update research loop to call telegram_osint.py
3. Automated cross-source verification

### Option 3: Hybrid Approach (Recommended)
1. Monitor Telegram manually for breaking news
2. Use research loops for deep analysis
3. Cross-verify through multiple sources

## Security Considerations

### Data Handling
- All Telegram data is READ-ONLY
- No message sending capabilities
- Session files stored locally only
- Rate limiting prevents abuse

### Privacy
- Uses your personal Telegram account
- Channels can see you joined (if public)
- Consider using dedicated account for OSINT

### Operational Security  
- Don't join sensitive channels from main account
- Be aware of digital footprint
- Focus on public/semi-public intelligence sources

## Integration Example

```python
# In research loop task
osint_data = await gather_multi_source_intelligence()
threat_level = osint_data["consolidated_assessment"]["overall_threat_level"]

if threat_level >= 7:
    # Trigger additional market hedges
    additional_trades = trader.iran_escalation_trades(threat_level, "1_week")
    # Execute trades via Tradier API
```

This provides comprehensive intelligence gathering while maintaining security boundaries.
"""

async def demo_integration():
    """Demo the multi-source intelligence integration"""
    
    print("🔍 Multi-Source OSINT Integration Demo")
    print("=" * 50)
    
    # Simulated configuration
    config = {
        "telegram": None,  # Would contain API credentials
        "twitter": True,
        "market_data": True
    }
    
    osint = MultiSourceOSINT()
    
    # Generate sample intelligence report
    sample_report = {
        "timestamp": datetime.now().isoformat(),
        "sources": {
            "telegram": {
                "status": "operational",
                "messages_analyzed": 15,
                "threat_indicators": {
                    "escalation_signals": 4,
                    "iranian_activity": 2,
                    "oil_energy_events": 1
                },
                "threat_level": 6
            },
            "twitter": {
                "status": "configured", 
                "note": "Execute via Grok model"
            },
            "market": {
                "status": "configured",
                "note": "Pull via Tradier API"
            }
        },
        "consolidated_assessment": {
            "overall_threat_level": 6,
            "confidence": "medium",
            "primary_concerns": [
                "Multiple escalation signals detected",
                "Increased Iranian military activity"
            ]
        }
    }
    
    print("📊 Sample Intelligence Report:")
    print(json.dumps(sample_report, indent=2))
    
    print(f"\n🎯 Research Loop Integration:")
    print(f"- Threat Level: {sample_report['consolidated_assessment']['overall_threat_level']}/10")
    print(f"- Recommended Action: {'Aggressive positioning' if sample_report['consolidated_assessment']['overall_threat_level'] >= 7 else 'Moderate hedging'}")
    
    print(f"\n📋 Setup Guide:")
    setup_guide = create_telegram_setup_guide()
    with open('/tmp/telegram_setup_guide.md', 'w') as f:
        f.write(setup_guide)
    print(f"   Saved to: /tmp/telegram_setup_guide.md")

if __name__ == "__main__":
    asyncio.run(demo_integration())