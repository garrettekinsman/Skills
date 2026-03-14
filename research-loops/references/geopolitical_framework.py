#!/usr/bin/env python3
"""
Geopolitical Intelligence Framework for Research Loops
Monitors OSINT sources and translates geopolitical events into market implications
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any
from dataclasses import dataclass

@dataclass
class GeopoliticalEvent:
    """A geopolitical event with market implications"""
    timestamp: str
    region: str  # "middle_east", "eastern_europe", "south_china_sea", etc.
    event_type: str  # "escalation", "de_escalation", "conflict", "sanctions", etc.
    severity: int  # 1-10 scale
    actors: List[str]  # Countries/entities involved
    description: str
    source_type: str  # "osint", "official", "media", "social"
    confidence: float  # 0.0-1.0
    market_implications: List[str]
    
class GeopoliticalMonitor:
    """Monitor geopolitical events and assess market impact"""
    
    # Event severity thresholds
    SEVERITY_THRESHOLDS = {
        "minor": (1, 3),      # Diplomatic protests, minor incidents
        "moderate": (4, 6),   # Sanctions, military posturing 
        "major": (7, 8),      # Limited military action, major sanctions
        "critical": (9, 10)   # Full conflict, major power confrontation
    }
    
    # Market impact mappings
    MARKET_IMPLICATIONS = {
        "middle_east_conflict": {
            "oil": "bullish",      # WTI, Brent crude
            "gold": "bullish",     # Safe haven demand
            "defense": "bullish",  # RTX, LMT, NOC
            "airlines": "bearish", # Higher fuel costs
            "risk_assets": "bearish"  # Tech, growth stocks
        },
        "china_taiwan_tension": {
            "semiconductor": "bearish",  # Taiwan exposure
            "defense": "bullish",
            "safe_havens": "bullish",
            "asia_pacific": "bearish"
        },
        "russia_escalation": {
            "energy": "bullish",   # Natural gas, oil
            "wheat": "bullish",    # Food security
            "defense": "bullish",
            "emerging_markets": "bearish"
        },
        "iran_israel_conflict": {
            "oil": "very_bullish",  # Strait of Hormuz risk
            "gold": "bullish",
            "defense": "bullish", 
            "regional_airlines": "bearish",
            "shipping": "mixed"    # Higher rates but route risk
        }
    }
    
    def __init__(self):
        self.active_events = []
        self.event_history = []
        self.escalation_indicators = {
            "military_movements": [],
            "diplomatic_language": [],
            "economic_measures": [],
            "alliance_responses": []
        }
    
    def assess_iran_situation(self) -> Dict[str, Any]:
        """Specific assessment for current Iran situation"""
        
        # Key indicators to monitor
        indicators = {
            "irgc_activity": {
                "proxy_movements": "hezbollah, houthis, iraqi_militias",
                "naval_activity": "strait_of_hormuz_patrols", 
                "missile_tests": "ballistic_medium_range"
            },
            "israeli_posture": {
                "military_readiness": "reserves_called_up",
                "diplomatic_messaging": "red_lines_stated",
                "alliance_coordination": "us_assets_deployed"
            },
            "escalation_triggers": [
                "israeli_strike_on_iran_nuclear",
                "iran_closure_strait_hormuz", 
                "mass_casualty_proxy_attack",
                "iran_nuclear_breakout"
            ],
            "de_escalation_signals": [
                "diplomatic_engagement",
                "proxy_restraint",
                "economic_cooperation_talks"
            ]
        }
        
        # Market preparation scenarios
        scenarios = {
            "limited_tit_for_tat": {
                "probability": 0.4,
                "oil_impact": "+5-15%",
                "duration": "1-2 weeks",
                "trades": ["sector_etf_1 calls", "sector_etf_2 calls", "commodity_etf calls"]
            },
            "sustained_conflict": {
                "probability": 0.3, 
                "oil_impact": "+20-40%",
                "duration": "1-3 months",
                "trades": ["Oil futures", "Defense stocks", "Safe havens"]
            },
            "strait_closure": {
                "probability": 0.1,
                "oil_impact": "+50-100%",
                "duration": "Weeks to months",
                "trades": ["Emergency oil reserves", "Global recession hedge"]
            },
            "diplomatic_resolution": {
                "probability": 0.2,
                "oil_impact": "-5 to -15%",
                "duration": "Days",
                "trades": ["Short oil", "Long risk assets"]
            }
        }
        
        return {
            "situation": "iran_israel_escalation_risk",
            "current_severity": 6,  # Moderate-high
            "key_indicators": indicators,
            "scenarios": scenarios,
            "recommended_monitoring": [
                "@sentdefender",      # Defense/OSINT Twitter
                "@IntelCrab",         # OSINT aggregator  
                "@WarMonitors",       # Real-time conflict updates
                "@ElintNews",         # Intel/aviation tracking
                "@YWNReporter"        # Regional news
            ]
        }
    
    def generate_osint_queries(self, event_type: str, region: str) -> List[str]:
        """Generate Twitter/X search queries for OSINT monitoring"""
        
        base_queries = {
            "iran_israel": [
                "Iran Israel military OR strike OR attack OR retaliation",
                "IRGC Hezbollah OR proxy OR militia activity",  
                "Strait Hormuz OR oil tanker OR naval",
                "Netanyahu Iran OR nuclear OR red line",
                "Iron Dome OR missile OR rocket alert Israel",
                "US Navy Persian Gulf OR carrier OR deployment"
            ],
            "china_taiwan": [
                "PLA Taiwan Strait OR military exercise OR incursion",
                "TSMC semiconductor OR chip OR supply chain risk",
                "US Navy South China Sea OR patrol OR transit",
                "Xi Jinping Taiwan OR reunification OR force"
            ],
            "russia_ukraine": [
                "Russia Ukraine escalation OR nuclear OR red line",
                "NATO Article 5 OR troops OR weapons", 
                "Energy pipeline OR gas OR sanctions",
                "Putin mobilization OR conscription OR military"
            ]
        }
        
        return base_queries.get(event_type, [])
    
    def backtest_geopolitical_events(self, historical_events: List[Dict]) -> Dict[str, Any]:
        """Backtest how markets reacted to similar geopolitical events"""
        
        # Historical geopolitical market reactions
        historical_reactions = {
            "gulf_war_1991": {
                "oil": "+120% (Jan-Mar 1991)",
                "gold": "+8% peak",
                "spy": "-17% (Aug 1990-Jan 1991)",
                "lessons": "Swift resolution = quick reversal"
            },
            "iraq_invasion_2003": {
                "oil": "+70% (2002-2004)", 
                "defense": "RTX +45%, LMT +38%",
                "spy": "Sold news, rallied during war",
                "lessons": "Anticipation > actual event"
            },
            "iran_tanker_attacks_2019": {
                "oil": "+4% same day, +15% over 2 weeks",
                "shipping": "EURN +8%, FRO +12%",
                "duration": "2-3 weeks before normalization",
                "lessons": "Temporary premium unless sustained"
            },
            "russia_ukraine_2022": {
                "oil": "+25% (Feb-Mar 2022)",
                "wheat": "+50% (supply shock)",
                "defense": "LMT +30%, RTX +25%",
                "tech": "tech_etf -20% (risk-off)",
                "lessons": "Sustained conflict = persistent impact"
            },
            "soleimani_assassination_2020": {
                "oil": "+4% overnight, +8% peak",
                "gold": "+2% same day",
                "vix": "+23% to 18.5",
                "duration": "5 trading days to normalize",
                "lessons": "Single events fade without follow-up"
            }
        }
        
        # Pattern analysis
        patterns = {
            "oil_reactions": {
                "immediate": "+2% to +8% same day",
                "sustained_if": "Supply disruption OR prolonged conflict",
                "fade_if": "No follow-up events within 7-10 days"
            },
            "defense_stocks": {
                "immediate": "+3% to +10% same day",
                "sustained_if": "Multi-year conflict OR arms sales",
                "leaders": "RTX (air defense), LMT (missiles), NOC (naval)"
            },
            "safe_havens": {
                "gold": "+1% to +5% same day",
                "bonds": "Flight to TLT, yields down",
                "currencies": "USD up, emerging markets down"
            },
            "risk_assets": {
                "tech": "-2% to -8% same day",
                "emerging": "-5% to -15%", 
                "recovery": "5-15 days if no escalation"
            }
        }
        
        return {
            "historical_events": historical_reactions,
            "reaction_patterns": patterns,
            "trading_insights": {
                "buy_on_fear": "Often overreacts initially",
                "sell_on_news": "Anticipation > actual event", 
                "time_horizon": "Days for single events, months for conflicts",
                "sector_rotation": "Defense up, discretionary down, energy mixed"
            }
        }

def create_geopolitical_research_config(region: str, event_type: str) -> Dict[str, Any]:
    """Create a research loop config for geopolitical analysis"""
    
    config = {
        "domain": "intelligence",
        "mode": "streaming",  # Real-time monitoring
        "problem_statement": f"Assess {region} {event_type} risks and market implications",
        "success_criteria": [
            "Credible threat assessment with confidence scores",
            "Specific market trades with risk/reward ratios", 
            "Timeline for key escalation/de-escalation indicators",
            "Cross-verified intelligence from ≥3 sources"
        ],
        "resources": {
            "time_budget_minutes": 120,
            "token_budget": 200000,  # Larger for comprehensive OSINT
            "cost_budget_usd": 8.00,
            "data_sources": ["twitter_osint", "news_feeds", "official_sources", "tradier"],
            "models": ["xai/grok-3", "anthropic/claude-sonnet-4"]  # Grok for Twitter data
        },
        "real_time": {
            "enabled": True,
            "update_frequency_seconds": 300,  # 5 minute updates
            "significance_threshold": 0.05,   # High sensitivity
            "alert_channels": ["discord"]
        },
        "geopolitical_specific": {
            "region": region,
            "event_type": event_type,
            "osint_sources": [
                "@sentdefender", "@IntelCrab", "@WarMonitors", 
                "@ElintNews", "@YWNReporter", "@Conflicts"
            ],
            "escalation_indicators": [
                "military_movements",
                "diplomatic_language_shifts", 
                "economic_measures",
                "alliance_responses"
            ],
            "market_sectors": {
                "bullish": ["energy", "defense", "safe_havens"],
                "bearish": ["airlines", "tourism", "risk_assets"],
                "mixed": ["shipping", "tech", "emerging_markets"]
            }
        },
        "validation": {
            "cross_source_required": True,
            "adversarial_testing": True,
            "source_credibility": True,
            "timeline_analysis": True,
            "bias_detection": True
        },
        "output": {
            "format": "brief",
            "delivery": ["file", "discord"],
            "include_threat_assessment": True,
            "include_market_trades": True,
            "include_confidence_scores": True,
            "update_frequency": "every_significant_development"
        }
    }
    
    return config

# Example usage and testing
if __name__ == "__main__":
    monitor = GeopoliticalMonitor()
    
    # Current Iran situation analysis
    iran_assessment = monitor.assess_iran_situation()
    print("Iran Situation Assessment:")
    print(json.dumps(iran_assessment, indent=2))
    
    # Generate research loop config
    config = create_geopolitical_research_config("middle_east", "iran_israel_escalation")
    print("\nGeopolitical Research Loop Config:")
    print(json.dumps(config, indent=2))
    
    # Historical backtesting
    backtest_results = monitor.backtest_geopolitical_events([])
    print("\nHistorical Market Reactions:")
    for event, data in backtest_results["historical_events"].items():
        print(f"{event}: {data}")